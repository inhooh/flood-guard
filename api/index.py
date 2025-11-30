from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import numpy as np
import os
import json

# --- Firebase Admin SDK 설정 ---
db = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    # 1. 환경 변수 (Vercel 배포 환경)
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore 연결 성공 (환경 변수)!")
        
    # 2. 로컬 파일 (개발 환경 - serviceAccountKey.json이 루트에 있어야 함)
    # api 폴더 내에 있다면 '../serviceAccountKey.json'으로 경로 수정 필요할 수 있음
    # 여기서는 안전하게 절대 경로 탐색 시도
    elif os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore 연결 성공 (로컬 파일)!")
    elif os.path.exists('../serviceAccountKey.json'):
        cred = credentials.Certificate('../serviceAccountKey.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("🔥 Firebase Firestore 연결 성공 (상위 폴더 로컬 파일)!")
        
    else:
        print("⚠️ Firebase 키 없음. 로컬 데이터 모드로 동작합니다.")
        
except Exception as e:
    print(f"⚠️ Firebase 초기화 에러: {e}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = 'c965d7cee76ede7e4be93efd1040a83589b93b4e5c25bd81006e81901d66b809'

class LocationRequest(BaseModel):
    location: str
    lat: float
    lon: float

# --- 로컬 데이터 (DB 연결 실패 시 비상용) ---
KOREAN_CITIES_FLAT_FALLBACK = {
    '강남구': (37.5172, 127.0474, 61, 126, 0.5),
    '해운대구': (35.1631, 129.1636, 102, 42, 1.0),
}

# --- 1. 도시 검색 (DB 우선) ---
def find_city_data(location_keyword):
    # 1. DB 검색
    if db:
        try:
            # Firestore에서 모든 문서를 스트리밍하여 검색
            # (데이터 양이 많아지면 .where() 쿼리로 변경 권장)
            docs = db.collection('cities').stream()
            for doc in docs:
                city = doc.to_dict()
                # '강남구'가 '서울 강남구' 검색어에 포함되는지 확인
                if city.get('name') and city.get('name') in location_keyword:
                    print(f"🔍 DB 매칭 성공: {city.get('name')}")
                    return (city['lat'], city['lon'], city['nx'], city['ny'], city['base_depth'])
        except Exception as e:
            print(f"⚠️ DB 검색 실패 (로컬 전환): {e}")

    # 2. 로컬 검색 (Fallback)
    for name, data in KOREAN_CITIES_FLAT_FALLBACK.items():
        if name in location_keyword:
            print(f"🔍 로컬 매칭 성공: {name}")
            return data
    return None

# --- 2. 현재 날씨 (초단기실황) ---
def get_current_weather(nx, ny):
    try:
        now = datetime.now()
        # 45분 이전에는 1시간 전 데이터를 요청
        if now.minute < 45:
            target = now - timedelta(hours=1)
        else:
            target = now
        
        base_date = target.strftime('%Y%m%d')
        base_time = target.strftime('%H00')

        url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        params = {
            'serviceKey': API_KEY, 'pageNo': '1', 'numOfRows': '10', 'dataType': 'JSON',
            'base_date': base_date, 'base_time': base_time, 'nx': str(nx), 'ny': str(ny)
        }
        
        res = requests.get(url, params=params, timeout=3)
        if res.status_code == 200:
            items = res.json()['response']['body']['items']['item']
            rain, temp, wind = 0, 0, 0
            for item in items:
                cat = item['category']
                val = float(item['obsrValue'])
                if cat == 'RN1': rain = val
                elif cat == 'T1H': temp = val
                elif cat == 'WSD': wind = val
            return rain, temp, wind
    except:
        pass
    return 0, 0, 0

# --- 3. [NEW] 미래 예보 (단기예보) ---
def get_forecast_weather(nx, ny):
    """향후 6시간 내 최대 예상 강수량을 조회"""
    try:
        # 단기예보는 02:00, 05:00... 3시간 간격으로 나옴
        now = datetime.now()
        base_times = [2, 5, 8, 11, 14, 17, 20, 23]
        
        target_hour = now.hour
        # 발표 직후(10분 내)에는 데이터가 없을 수 있어 1시간 전 기준 적용
        if now.minute < 10: 
            target_hour -= 1
            
        # 현재 시간보다 작거나 같은 것 중 가장 최근 시간 찾기
        valid_times = [t for t in base_times if t <= target_hour]
        
        if not valid_times: # 자정 지나서 02시 이전인 경우 -> 전날 23시
            base_hour = 23
            base_date = (now - timedelta(days=1)).strftime('%Y%m%d')
        else:
            base_hour = valid_times[-1]
            base_date = now.strftime('%Y%m%d')
            
        base_time = f"{base_hour:02d}00"
        
        url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
        params = {
            'serviceKey': API_KEY, 'pageNo': '1', 'numOfRows': '60', 'dataType': 'JSON',
            'base_date': base_date, 'base_time': base_time, 'nx': str(nx), 'ny': str(ny)
        }
        
        print(f"🔮 미래 예보 요청: {base_date} {base_time}")
        res = requests.get(url, params=params, timeout=5)
        
        max_rain_forecast = 0.0
        
        if res.status_code == 200:
            items = res.json()['response']['body']['items']['item']
            # 향후 데이터 중 강수량(PCP) 확인
            for item in items:
                if item['category'] == 'PCP':
                    val_str = item['fcstValue']
                    if val_str == '강수없음': val = 0.0
                    elif 'mm' in val_str: val = float(val_str.replace('mm',''))
                    else: val = float(val_str)
                    
                    if val > max_rain_forecast:
                        max_rain_forecast = val
                        
            print(f"🔮 향후 최대 강수량 예측: {max_rain_forecast}mm")
            return max_rain_forecast
            
    except Exception as e:
        print(f"⚠️ 예보 조회 실패: {e}")
        
    return 0.0

# --- 4. 통합 위험도 계산 ---
def calculate_risk(current_rain, future_rain, base_depth):
    # 가중치: 현재 비(60%) + 미래 비(40%)
    rain_score = min(100, (current_rain / 30) * 100) # 시간당 30mm면 만점
    future_score = min(100, (future_rain / 50) * 100) # 예보는 50mm 기준
    
    combined_rain_score = (rain_score * 0.6) + (future_score * 0.4)
    depth_score = min(50, base_depth * 10)
    
    total = (combined_rain_score * 0.7) + (depth_score * 0.3)
    return min(99, int(total))

# --- 5. API 엔드포인트 ---
@app.post("/predict")
@app.post("/api/predict")
def predict_flood_risk(request: LocationRequest):
    print(f"📡 분석 요청: {request.location}")
    
    # 1. 도시 데이터 찾기
    city_data = find_city_data(request.location)
    
    if city_data:
        lat, lon, nx, ny, base_depth = city_data
    else:
        print("⚠️ 도시 미확인 (기본값 서울)")
        nx, ny, base_depth = 60, 127, 0.5
        
    # 2. 날씨 데이터 조회
    curr_rain, temp, wind = get_current_weather(nx, ny)
    future_rain = get_forecast_weather(nx, ny)
    
    # 3. 위험도 계산
    risk_score = calculate_risk(curr_rain, future_rain, base_depth)
    
    # 4. 코멘트 생성
    comment = "현재와 미래 날씨 모두 안전합니다."
    if risk_score >= 80:
        comment = f"🚨 [대피 권고] 현재 비({curr_rain}mm)와 향후 폭우({future_rain}mm)가 겹쳐 침수 위험이 매우 높습니다!"
    elif future_rain > 30:
        comment = f"⚠️ [예비 경보] 지금은 괜찮지만, 곧 강한 비({future_rain}mm)가 예보되어 있습니다. 미리 대비하세요."
    elif curr_rain > 0:
        comment = f"☔ [우천] 비가 오고 있습니다({curr_rain}mm). 배수구를 확인하세요."
        
    return {
        "riskScore": risk_score,
        "waterLevel": base_depth + (curr_rain * 0.01) + (future_rain * 0.005),
        "rainfall": curr_rain,
        "forecastRain": future_rain, 
        "windSpeed": wind,
        "temperature": temp,
        "comment": comment
    }