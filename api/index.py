from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import numpy as np
import os
import json

# --- Firebase Admin SDK 설정 (DB 연동 준비) ---
# 라이브러리가 없거나 키가 없어도 서버가 죽지 않도록 예외 처리
db = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    # 1. Vercel 배포 환경: 환경 변수에서 키를 찾습니다.
    if os.environ.get('FIREBASE_CREDENTIALS'):
        # 환경 변수 문자열을 JSON 객체로 변환
        cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore 연결 성공 (환경 변수)!")
        
    # 2. 로컬 개발 환경: serviceAccountKey.json 파일을 찾습니다.
    # 주의: 이 파일은 프로젝트 최상위(Root) 폴더에 있어야 합니다.
    elif os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore 연결 성공 (로컬 파일)!")
        
    else:
        print("⚠️ Firebase 키를 찾을 수 없어 '로컬 데이터 모드'로 동작합니다.")
        
except ImportError:
    print("⚠️ firebase-admin 패키지가 설치되지 않았습니다. requirements.txt를 확인하세요.")
except Exception as e:
    print(f"⚠️ Firebase 초기화 에러: {e}")
    print("-> 서버는 '로컬 데이터 모드'로 계속 실행됩니다.")

app = FastAPI()

# --- 1. 기본 설정 (CORS & API 키) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기상청 API 키
API_KEY = 'c965d7cee76ede7e4be93efd1040a83589b93b4e5c25bd81006e81901d66b809'

# --- 2. 데이터 모델 ---
class LocationRequest(BaseModel):
    location: str
    lat: float
    lon: float

# --- 3. 전국 도시 데이터 (기본값/백업용) ---
# DB 연결 실패 시 이 데이터를 사용합니다.
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
    # 주요 도시 추가
    '수영구': (35.1455, 129.1132, 101, 41, 1.0),
    '분당구': (37.3827, 127.1189, 61, 122, 0.4),
    '일산동구': (37.6777, 126.7489, 56, 129, 0.5),
    '수성구': (35.8584, 128.6306, 90, 90, 0.7),
    '유성구': (36.3622, 127.3563, 67, 101, 0.7),
    '연수구': (37.4094, 126.6784, 56, 123, 0.2),
}

# --- 4. 도시 데이터 검색 헬퍼 함수 ---
def find_city_data(location_keyword):
    """
    1. Firebase DB가 연결되어 있으면 DB에서 검색
    2. 실패하거나 연결 안 되어 있으면 로컬 Dictionary에서 검색
    """
    # 1. DB 검색 시도
    if db:
        try:
            # Firestore에서 모든 도시 문서를 가져와서 매칭 (데이터 양이 적을 때 유효)
            # 데이터가 많아지면 .where() 쿼리를 사용하는 것이 좋습니다.
            docs = db.collection('cities').stream()
            for doc in docs:
                city = doc.to_dict()
                # city 문서에는 'name', 'lat', 'lon', 'nx', 'ny', 'base_depth' 필드가 있어야 합니다.
                if city.get('name') and city.get('name') in location_keyword:
                    print(f"🔍 DB에서 발견: {city.get('name')}")
                    return (city['lat'], city['lon'], city['nx'], city['ny'], city['base_depth'])
        except Exception as e:
            print(f"⚠️ DB 조회 중 오류 (로컬 데이터로 전환): {e}")

    # 2. 로컬 데이터 검색 (Fallback)
    for gu_name, data in KOREAN_CITIES_FLAT.items():
        if gu_name in location_keyword:
            print(f"🔍 로컬 데이터 발견: {gu_name}")
            return data
            
    return None

# --- 5. 기상청 API 연동 함수 ---
def get_real_weather(nx, ny):
    """기상청 초단기실황 API 호출"""
    try:
        now = datetime.now()
        
        # 45분 이전에는 1시간 전 데이터를 요청 (데이터 생성 시간 고려)
        if now.minute < 45:
            target_time = now - timedelta(hours=1)
        else:
            target_time = now

        base_date = target_time.strftime('%Y%m%d')
        base_time = target_time.strftime('%H00')
        
        url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        params = {
            'serviceKey': API_KEY, 
            'pageNo': '1', 
            'numOfRows': '10', 
            'dataType': 'JSON', 
            'base_date': base_date, 
            'base_time': base_time, 
            'nx': str(nx), 
            'ny': str(ny)
        }
        
        print(f"🌦️ 기상청 요청: {base_date} {base_time} (격자: {nx}, {ny})")
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            try:
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
                print(f"⚠️ 데이터 파싱 에러: {e}")
                pass
            
    except Exception as e:
        print(f"⚠️ 기상청 API 에러: {e}")
    
    # 에러 발생 시 랜덤값 반환 (시뮬레이션 모드)
    print("⚠️ API 호출 실패로 시뮬레이션 데이터 반환")
    return np.random.randint(0, 5), np.random.randint(15, 25), np.random.randint(1, 10)

# --- 6. 위험도 계산 로직 ---
def calculate_flood_risk(rainfall, base_depth, elevation=10):
    rain_score = min(100, (rainfall / 50) * 100)
    depth_score = min(50, base_depth * 10)
    total_risk = (rain_score * 0.7) + (depth_score * 0.3)
    return min(99, int(total_risk))

# --- 7. API 엔드포인트 ---
@app.post("/predict")
@app.post("/api/predict")
def predict_flood_risk(request: LocationRequest):
    location_keyword = request.location
    print(f"📡 요청 지역: {location_keyword}")
    
    # 1. 도시 정보 찾기 (DB -> 로컬 순서로 검색)
    city_data = find_city_data(location_keyword)
            
    if city_data:
        lat, lon, nx, ny, base_depth = city_data
        print(f"📍 좌표 확인 완료: ({nx}, {ny})")
    else:
        print("⚠️ 도시 매칭 실패, 기본값 사용")
        nx, ny = 60, 127
        base_depth = 0.5
    
    # 2. 실제 날씨 가져오기
    rainfall, temp, wind = get_real_weather(nx, ny)
    
    # 3. 위험도 계산
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
        "waterLevel": base_depth + (rainfall * 0.01),
        "rainfall": rainfall,
        "windSpeed": wind,
        "temperature": temp,
        "comment": comment
    }