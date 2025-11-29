import React, { useState, useEffect } from 'react';
import { MapPin, Droplets, Wind, Thermometer, ChevronRight, BarChart3, Info, ShieldAlert, Waves, Server, Activity } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

// --- Mock Data ---
const MOCK_HISTORY_DATA = [
  { time: '06:00', level: 1.2, rain: 5 },
  { time: '09:00', level: 1.4, rain: 12 },
  { time: '12:00', level: 1.8, rain: 25 },
  { time: '15:00', level: 2.1, rain: 18 },
  { time: '18:00', level: 1.9, rain: 8 },
  { time: '21:00', level: 1.5, rain: 2 },
];

// --- Components ---

const Card = ({ children, className = "" }) => (
  <div className={`bg-white/80 backdrop-blur-md rounded-2xl shadow-lg border border-white/20 p-6 ${className}`}>
    {children}
  </div>
);

const RiskGauge = ({ riskScore }) => {
  const radius = 80;
  const stroke = 12;
  const normalizedRadius = radius - stroke * 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (riskScore / 100) * circumference;

  let color = "stroke-emerald-500";
  let status = "안전";
  let bgColor = "bg-emerald-50";
  
  if (riskScore > 30) { color = "stroke-yellow-500"; status = "주의"; bgColor = "bg-yellow-50"; }
  if (riskScore > 70) { color = "stroke-rose-600"; status = "위험"; bgColor = "bg-rose-50"; }

  return (
    <div className="flex flex-col items-center justify-center relative">
      <div className="relative flex items-center justify-center">
        <svg height={radius * 2} width={radius * 2} className="rotate-[-90deg]">
          <circle className="stroke-gray-200" strokeWidth={stroke} fill="transparent" r={normalizedRadius} cx={radius} cy={radius} />
          <circle className={`${color} transition-all duration-1000 ease-out`} strokeWidth={stroke} strokeDasharray={circumference + ' ' + circumference} style={{ strokeDashoffset }} strokeLinecap="round" fill="transparent" r={normalizedRadius} cx={radius} cy={radius} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-4xl font-bold text-slate-800">{riskScore}</span>
          <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Risk Score</span>
        </div>
      </div>
      <div className={`mt-4 px-4 py-1.5 rounded-full text-sm font-bold ${bgColor} ${color.replace('stroke-', 'text-')}`}>
        {status} 단계
      </div>
    </div>
  );
};

const StatItem = ({ icon: Icon, label, value, unit, trend }) => (
  <div className="flex items-center p-4 bg-white rounded-xl shadow-sm border border-slate-100 hover:shadow-md transition-shadow">
    <div className="p-3 bg-blue-50 rounded-lg text-blue-600 mr-4">
      <Icon size={24} />
    </div>
    <div>
      <p className="text-sm text-slate-500 font-medium">{label}</p>
      <div className="flex items-baseline">
        <span className="text-2xl font-bold text-slate-800">{value}</span>
        <span className="text-sm text-slate-400 ml-1">{unit}</span>
      </div>
      {trend && <p className="text-xs text-emerald-500 mt-1 font-medium">{trend}</p>}
    </div>
  </div>
);

const App = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  
  const [riskData, setRiskData] = useState(null);
  const [weatherData, setWeatherData] = useState(null);
  const [coords, setCoords] = useState({ lat: 37.5665, lon: 126.9780 }); // 서울 시청
  const [isLiveMode, setIsLiveMode] = useState(false); // 백엔드 연결 상태

  // [2단계] 무료 주소 검색 API (Nominatim)
  const fetchCoordinates = async (location) => {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${location}&limit=1`);
      const data = await response.json();
      if (data && data.length > 0) {
        return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
      }
      return null;
    } catch (e) {
      console.error("주소 검색 실패", e);
      return null;
    }
  };

  // [3단계 핵심] 백엔드(Python)에서 데이터 가져오기
  const fetchFloodRisk = async (location, lat, lon) => {
    try {
      // ⚠️ 중요: 로컬 주소(http://127.0.0.1...)를 지우고 상대 경로 '/api/predict'만 사용합니다.
      // 이렇게 하면 Vercel이 자동으로 같은 도메인의 백엔드로 연결합니다.
      const response = await fetch('/api/predict', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ location, lat, lon }),
      });

      if (!response.ok) {
        throw new Error(`백엔드 응답 실패: ${response.status}`);
      }

      const data = await response.json();
      setIsLiveMode(true); // 연결 성공 시 라이브 모드 활성화
      return data;

    } catch (error) {
      console.warn("백엔드 연결 실패 (시뮬레이션 모드로 전환):", error);
      setIsLiveMode(false);
      
      // 연결 실패 시: 기존처럼 시뮬레이션 데이터 반환 (Fallback)
      return {
        riskScore: Math.floor(Math.random() * 40) + 50,
        waterLevel: (Math.random() * 3 + 1).toFixed(1),
        rainfall: Math.floor(Math.random() * 100) + 50,
        windSpeed: Math.floor(Math.random() * 20) + 5,
        temperature: Math.floor(Math.random() * 15) + 10,
        comment: "현재 백엔드 서버와 연결할 수 없어 시뮬레이션 데이터를 보여줍니다."
      };
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchTerm) return;
    
    setLoading(true);
    
    try {
      // 1. 주소 검색
      const newCoords = await fetchCoordinates(searchTerm);
      let currentCoords = coords;
      if (newCoords) {
        setCoords(newCoords);
        currentCoords = newCoords;
      }

      // 2. 백엔드(또는 시뮬레이션) 데이터 요청
      // 딜레이를 살짝 주어 로딩 느낌 구현 (실제 API가 빠르면 삭제 가능)
      await new Promise(resolve => setTimeout(resolve, 800)); 

      const result = await fetchFloodRisk(searchTerm, currentCoords.lat, currentCoords.lon);

      // 3. 데이터 적용
      setWeatherData({
        rainfall: result.rainfall,
        windSpeed: result.windSpeed,
        temperature: result.temperature,
      });

      setRiskData({
        location: searchTerm,
        riskScore: result.riskScore,
        waterLevel: result.waterLevel,
        comment: result.comment
      });
      
      setAnalyzed(true);
    } catch (error) {
      console.error("분석 중 오류 발생:", error);
      alert("데이터를 불러오는 중 문제가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const getMapUrl = (lat, lon) => {
    const bbox = `${lon - 0.01},${lat - 0.01},${lon + 0.01},${lat + 0.01}`;
    return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lon}`;
  };

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900 selection:bg-blue-100 selection:text-blue-900">
      
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center space-x-2">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Waves className="text-white h-5 w-5" />
              </div>
              <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-700 to-cyan-500">
                DABAN FloodGuard AI
              </span>
            </div>
            <div className="hidden md:flex space-x-8 text-sm font-medium text-slate-600">
              <a href="#" className="hover:text-blue-600 transition-colors">대시보드</a>
              <a href="#" className="hover:text-blue-600 transition-colors">실시간 지도</a>
              <a href="#" className="hover:text-blue-600 transition-colors">예측 리포트</a>
            </div>
            <button className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors">
              로그인
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Search Section */}
        <div className={`transition-all duration-700 ${analyzed ? 'py-8' : 'py-20 flex flex-col items-center text-center'}`}>
          {!analyzed && (
            <>
              <h1 className="text-4xl md:text-5xl font-extrabold text-slate-900 mb-6 tracking-tight">
                당신의 지역은 <span className="text-blue-600">안전한가요?</span>
              </h1>
              <p className="text-lg text-slate-600 mb-10 max-w-2xl mx-auto leading-relaxed">
                DABAN이 만든 DABAN FloodGuard AI는 고객님들의 안전을 위해 AI 기반의 홍수 위험 예측 시스템으로 
                현재 위치의 침수 위험도와 실시간 기상 데이터를 분석하여 제공합니다.
              </p>
            </>
          )}

          <form onSubmit={handleSearch} className={`relative w-full ${analyzed ? 'max-w-full flex items-center justify-between mb-8' : 'max-w-2xl'}`}>
             <div className={`relative flex-grow ${analyzed ? 'max-w-md' : ''}`}>
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <MapPin className="h-5 w-5 text-slate-400" />
              </div>
              <input
                type="text"
                className="block w-full pl-11 pr-4 py-4 bg-white border border-slate-200 rounded-xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent shadow-sm transition-all text-lg"
                placeholder="지역명을 입력하세요 (예: 서울 강남구, 부산 해운대)"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <button 
                type="submit"
                className="absolute inset-y-2 right-2 px-6 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors flex items-center"
              >
                {loading ? (
                  <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <>분석하기</>
                )}
              </button>
            </div>
            {analyzed && (
               <div className="hidden md:flex items-center space-x-2 text-sm text-slate-500">
                  <span className={`flex items-center ${isLiveMode ? 'text-emerald-600' : 'text-slate-500'}`}>
                    <span className={`w-2 h-2 rounded-full mr-2 ${isLiveMode ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`}></span>
                    {isLiveMode ? 'AI 서버 실시간 연결됨' : '시뮬레이션 모드 (서버 미연결)'}
                  </span>
               </div>
            )}
          </form>
        </div>

        {/* Dashboard */}
        {analyzed && riskData && weatherData && (
          <div className="animate-fade-in-up space-y-6">
            
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Risk Gauge Card */}
              <Card className="col-span-1 lg:col-span-1 border-l-4 border-l-rose-500">
                <div className="flex flex-col h-full justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-slate-800 flex items-center mb-1">
                      <ShieldAlert className="w-5 h-5 text-rose-500 mr-2" />
                      침수 위험도 종합 분석
                    </h3>
                    <p className="text-sm text-slate-500 mb-6">최근 24시간 데이터 기반</p>
                  </div>
                  <div className="flex-grow flex items-center justify-center py-4">
                    <RiskGauge riskScore={riskData.riskScore} />
                  </div>
                </div>
              </Card>

              {/* Map Card */}
              <Card className="col-span-1 lg:col-span-2 p-0 overflow-hidden relative group h-[400px] z-0">
                <iframe
                  width="100%"
                  height="100%"
                  frameBorder="0"
                  scrolling="no"
                  marginHeight="0"
                  marginWidth="0"
                  src={getMapUrl(coords.lat, coords.lon)}
                  style={{ border: 1 }}
                  title="Realtime Map"
                ></iframe>
                
                <div className="absolute bottom-6 right-6 z-[400] bg-white/95 backdrop-blur rounded-xl p-4 shadow-xl border border-slate-100 max-w-xs pointer-events-none">
                    <h4 className="font-bold text-slate-800 text-sm mb-1">{riskData.location}</h4>
                    <p className="text-xs text-slate-500 leading-relaxed">
                        {isLiveMode ? '실시간 AI 서버 데이터 분석 중' : '시뮬레이션 데이터 표시 중'}
                    </p>
                </div>
              </Card>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatItem icon={Droplets} label="시간당 강수량" value={weatherData.rainfall} unit="mm" trend="▲ 증가세" />
              <StatItem icon={Waves} label="하천 수위" value={riskData.waterLevel} unit="m" trend="▲ 주의 필요" />
              <StatItem icon={Wind} label="풍속" value={weatherData.windSpeed} unit="m/s" />
              <StatItem icon={Thermometer} label="현재 기온" value={weatherData.temperature} unit="°C" />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card>
                <div className="flex items-center justify-between mb-6">
                    <h3 className="font-bold text-slate-800 flex items-center">
                        <BarChart3 className="w-5 h-5 mr-2 text-blue-500" />
                        수위 및 강수량 추이
                    </h3>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={MOCK_HISTORY_DATA}>
                      <defs>
                        <linearGradient id="colorLevel" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1}/>
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                      <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                      <RechartsTooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                      <Area type="monotone" dataKey="level" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorLevel)" name="수위 (m)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card>
                <div className="flex items-center justify-between mb-6">
                    <h3 className="font-bold text-slate-800 flex items-center">
                        <Info className="w-5 h-5 mr-2 text-purple-500" />
                        AI 분석 코멘트
                    </h3>
                </div>
                <div className="space-y-4">
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <h4 className="font-bold text-slate-800 text-sm mb-2">
                           {isLiveMode ? '📡 AI 모델 분석 완료' : '💡 시뮬레이션 분석 (서버 연결 안됨)'}
                        </h4>
                        <p className="text-sm text-slate-600">
                            {riskData.comment || "지형 및 기상 데이터를 종합적으로 분석한 결과, 침수 대비가 필요합니다."}
                        </p>
                    </div>
                </div>
              </Card>
            </div>

          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-slate-900 text-slate-400 py-12 mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
                <div>
                    <div className="flex items-center space-x-2 text-white mb-4">
                        <Waves className="h-6 w-6" />
                        <span className="text-xl font-bold">DABAN FloodGuard AI</span>
                    </div>
                    <p className="text-sm leading-relaxed">AI 기술을 활용하여 모두의 안전을 지키는<br/>차세대 재난 예방 플랫폼입니다.</p>
                </div>
                <div>
                    <h4 className="text-white font-bold mb-4">Service</h4>
                    <ul className="space-y-2 text-sm">
                        <li>실시간 침수 지도</li>
                        <li>위험 알림 구독</li>
                        <li>API 연동 문의</li>
                    </ul>
                </div>
                <div>
                    <h4 className="text-white font-bold mb-4">Contact</h4>
                    <ul className="space-y-2 text-sm">
                        <li>maverick525@naver.com</li>
                        <li>010-2540-3946</li>
                    </ul>
                </div>
            </div>
            <div className="border-t border-slate-800 pt-8 text-center">
                <p className="text-sm">copyright © 2025 DABAN. All rights reserved.</p>
            </div>
        </div>
      </footer>
    </div>
  );
};

export default App;