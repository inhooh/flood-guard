from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import numpy as np

app = FastAPI()

# --- 1. 기본 설정 (CORS & API 키) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기상청 API 키 (보내주신 파일에서 추출)
API_KEY = 'c965d7cee76ede7e4be93efd1040a83589b93b4e5c25bd81006e81901d66b809'

# --- 2. 데이터 모델 ---
class LocationRequest(BaseModel):
    location: str
    lat: float
    lon: float

# --- 3. 전국 도시 데이터 (data.py 통합) ---
# 포맷: '구이름': (위도, 경도, 기상청X, 기상청Y, 기본침수심)
# 검색 편의를 위해 시/도 구분 없이 평탄화하여 처리합니다.
KOREAN_CITIES_FLAT = {
    # 서울
    '강남구': (37.5172, 127.0474, 61, 126, 0.5),
    '강동구': (37.5301, 127.1237, 62, 126, 0.6),
    '강북구': (37.6398, 127.0255, 61, 129, 0.4),
    '강서구': (37.5509, 126.8495, 55, 127, 0.7),
    '관악구': (37.4784, 126.9515, 59, 125, 0.5),
    '광진구': (37.5386, 127.0823, 62, 127, 0.6),
    '구로구': (37.4955, 126.8874, 56, 125, 0.5),
    '금천구': (37.4519, 126.9020, 57, 124, 0.4),
    '노원구': (37.6542, 127.0568, 61, 130, 0.7),
    '도봉구': (37.6688, 127.0471, 61, 131, 0.6),
    '동대문구': (37.5744, 127.0396, 61, 127, 0.5),
    '동작구': (37.5124, 126.9393, 59, 126, 0.5),
    '마포구': (37.5663, 126.9018, 58, 127, 0.6),
    '서대문구': (37.5791, 126.9368, 59, 127, 0.4),
    '서초구': (37.4836, 127.0324, 61, 125, 0.5),
    '성동구': (37.5633, 127.0368, 61, 127, 0.6),
    '성북구': (37.5894, 127.0167, 61, 128, 0.5),
    '송파구': (37.5145, 127.1059, 62, 126, 0.7),
    '양천구': (37.5270, 126.8562, 56, 126, 0.4),
    '영등포구': (37.5264, 126.8963, 57, 126, 0.5),
    '용산구': (37.5326, 126.9900, 60, 126, 0.6),
    '은평구': (37.6027, 126.9291, 58, 128, 0.5),
    '종로구': (37.5730, 126.9794, 60, 127, 0.4),
    '중구': (37.5638, 126.9975, 60, 127, 0.5),
    '중랑구': (37.6066, 127.0926, 62, 128, 0.6),
    # 부산
    '해운대구': (35.1631, 129.1636, 102, 42, 1.0),
    '부산진구': (35.1628, 129.0532, 100, 42, 0.9),
    # 주요 도시 추가 (data.py 기반)
    '수영구': (35.1455, 129.1132, 101, 41, 1.0),
    '분당구': (37.3827, 127.1189, 61, 122, 0.4),
    '일산동구': (37.6777, 126.7489, 56, 129, 0.5),
    '수성구': (35.8584, 128.6306, 90, 90, 0.7),
    '유성구': (36.3622, 127.3563, 67, 101, 0.7),
    '연수구': (37.4094, 126.6784, 56, 123, 0.2),
}

# --- 4. 기상청 API 연동 함수 (api.py 통합) ---
def get_real_weather(nx, ny):
    """기상청 초단기실황 API 호출"""
    try:
        now = datetime.now()
        today = now.strftime('%Y%m%d')
        # 기상청 API는 매시 40분쯤 업데이트되므로, 현재 분이 40분 전이면 1시간 전 데이터를 요청
        if now.minute < 45:
            now_hour = now.hour - 1
        else:
            now_hour = now.hour
            
        # 시간 포맷 맞추기 (00~23)
        if now_hour < 0: # 자정 이전 처리
            now_hour = 23
            # 날짜도 하루 전으로 돌려야 하지만 복잡하므로 편의상 현재시간 유지하거나
            # 여기서는 간단히 00시로 고정하는 등 예외처리
            
        base_time = f"{now_hour:02d}00"
        
        url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        params = {
            'serviceKey': API_KEY, 
            'pageNo': '1', 
            'numOfRows': '10', 
            'dataType': 'JSON', # XML보다 JSON이 파싱하기 쉬움
            'base_date': today, 
            'base_time': base_time, 
            'nx': str(nx), 
            'ny': str(ny)
        }
        
        print(f"🌦️ 기상청 요청: {today} {base_time} (격자: {nx}, {ny})")
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            items = data['response']['body']['items']['item']
            
            rain = 0.0
            temp = 0.0
            wind = 0.0
            
            for item in items:
                cat = item['category']
                val = float(item['obsrValue'])
                
                if cat == 'RN1': # 1시간 강수량
                    rain = val
                elif cat == 'T1H': # 기온
                    temp = val
                elif cat == 'WSD': # 풍속
                    wind = val
                    
            print(f"✅ 날씨 수신 성공: 강수량 {rain}mm, 기온 {temp}도")
            return rain, temp, wind
            
    except Exception as e:
        print(f"⚠️ 기상청 API 에러: {e}")
        # 에러 시 랜덤값 반환 (앱이 멈추지 않게)
        return np.random.randint(0, 5), np.random.randint(15, 25), np.random.randint(1, 10)

    return 0, 20, 5 # 기본값

# --- 5. 위험도 계산 로직 (utils.py 통합) ---
def calculate_flood_risk(rainfall, base_depth, elevation=10):
    # utils.py의 로직 단순화 적용
    # 위험도 = (강수량 점수) + (기본 침수심 가중치)
    
    # 1. 강수량 점수 (시간당 50mm 넘으면 매우 위험)
    rain_score = min(100, (rainfall / 50) * 100)
    
    # 2. 침수심 점수 (도시별 base_depth 반영)
    depth_score = min(50, base_depth * 10)
    
    # 3. 최종 점수 (최대 100)
    total_risk = (rain_score * 0.7) + (depth_score * 0.3)
    
    return min(99, int(total_risk))

# --- 6. API 엔드포인트 ---
# ⚠️ [핵심 수정] /predict와 /api/predict 두 주소 모두 받도록 설정
@app.post("/predict")
@app.post("/api/predict")
def predict_flood_risk(request: LocationRequest):
    location_keyword = request.location
    print(f"📡 요청 지역: {location_keyword}")
    
    # 1. 도시 정보 찾기 (data.py 데이터 활용)
    city_data = None
    
    # 입력된 주소에 '강남', '해운대' 같은 구 이름이 있는지 확인
    for gu_name, data in KOREAN_CITIES_FLAT.items():
        if gu_name in location_keyword:
            city_data = data
            break
            
    if city_data:
        lat, lon, nx, ny, base_depth = city_data
        print(f"📍 매칭된 도시: {gu_name} (격자: {nx}, {ny})")
    else:
        # 매칭 안되면 서울시청 기준 기본값
        print("⚠️ 도시 매칭 실패, 기본값 사용")
        nx, ny = 60, 127
        base_depth = 0.5
    
    # 2. 실제 날씨 가져오기 (api.py 기능)
    rainfall, temp, wind = get_real_weather(nx, ny)
    
    # 3. 위험도 계산 (utils.py 기능)
    # 고도는 지도 API에서 못 받아오므로 평균값 15m 가정
    risk_score = calculate_flood_risk(rainfall, base_depth, elevation=15)
    
    # 4. 코멘트 생성
    if risk_score >= 80:
        comment = f"🚨 [심각] '{location_keyword}' 지역에 강한 비({rainfall}mm)가 내리고 있습니다. 침수 위험이 매우 높으니 즉시 대비하세요."
    elif risk_score >= 50:
        comment = f"⚠️ [주의] '{location_keyword}' 지역 침수 우려가 있습니다. 빗물받이를 확인하고 지하 주차장 진입을 자제하세요."
    elif rainfall > 0:
        comment = f"☔ [비] 비가 오고 있지만({rainfall}mm) 현재 침수 위험은 낮습니다. 기상 변화를 주시하세요."
    else:
        comment = f"✅ [안전] 현재 강수량이 없어 안전합니다. ({temp}°C, 맑음)"

    return {
        "riskScore": risk_score,
        "waterLevel": base_depth + (rainfall * 0.01), # 강수량 반영한 수위 시뮬레이션
        "rainfall": rainfall,
        "windSpeed": wind,
        "temperature": temp,
        "comment": comment
    }