import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta

# --- ページ設定 ---
st.set_page_config(page_title="完全自動・大口監視くん", layout="wide")

# セッション状態の初期化
if 'saved_odds' not in st.session_state: st.session_state['saved_odds'] = {}
if 'logs' not in st.session_state: st.session_state['logs'] = []
if 'is_running' not in st.session_state: st.session_state['is_running'] = False

# --- データ取得・解析関数 ---
def get_odds_data(race_id, mode="odds"):
    """mode="odds"で10分前用、mode="result"で確定後用を取得"""
    page = "odds" if mode == "odds" else "result"
    url = f"https://race.netkeiba.com/race/{page}.html?race_id={race_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('tr.HorseList')
        data = []
        for row in rows:
            name = (row.select_one('.HorseName') or row.select_one('.Horse_Name')).text.strip()
            win = (row.select_one('.WinOdds') or row.select_one('.Odds')).text.strip().replace('---', '0').replace('取消', '0')
            place = row.select_one('.PlaceOdds').text.split('-')[0].strip() if row.select_one('.PlaceOdds') else "0.0"
            data.append({"馬名": name, f"複勝_{mode}": float(place)})
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def get_race_schedule(date_code, venue):
    """当日の全12レースの発走時刻を自動取得する"""
    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    schedule = {}
    try:
        res = requests.get(url, headers=headers)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        # 指定会場のブロックを探す
        venue_names = {"05": "東京", "08": "京都", "10": "小倉", "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "06": "中山", "07": "中京", "09": "阪神"}
        v_name = venue_names.get(venue, "")
        
        # 簡易的に全IDを生成して各レースページから時間を取る（精度重視）
        for r in range(1, 13):
            rid = f"{date_code}{venue}{str(r).zfill(2)}"
            r_res = requests.get(f"https://race.netkeiba.com/race/summay.html?race_id={rid}", headers=headers)
            r_soup = BeautifulSoup(r_res.text, 'html.parser')
            time_str = r_soup.select_one('.RaceData01').text.split('発走')[0][-6:].strip() if r_soup.select_one('.RaceData01') else ""
            if ":" in time_str:
                schedule[rid] = time_str
        return schedule
    except:
        return {}

# --- メイン UI ---
st.title("🤖 10分前オッズ自動予約・監視システム")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ 監視設定")
    date_input = st.text_input("開催日(8桁)", value=datetime.now().strftime("%Y%m%d"))
    venue_input = st.selectbox("会場", ["05(東京)", "08(京都)", "10(小倉)"])[:2]
    
    if st.button("🚀 自動監視を開始する"):
        st.session_state['is_running'] = True
        st.session_state['schedule'] = get_race_schedule(date_input, venue_input)
        st.session_state['logs'].append(f"✅ {datetime.now().strftime('%H:%M')} 監視を開始しました")

    if st.button("📊 夜の答え合わせ（一括解析）"):
        if not st.session_state['saved_odds']:
            st.error("保存されたデータがありません。")
        else:
            all_results = []
            for rid, base_df in st.session_state['saved_odds'].items():
                now_df = get_odds_data(rid, mode="result")
                if not now_df.empty:
                    merged = pd.merge(now_df, base_df, on="馬名")
                    merged['下落率'] = (merged['複勝_odds'] - merged['複勝_result']) / merged['複勝_odds']
                    merged['レース'] = f"{rid[-2:]}R"
                    all_results.append(merged)
            
            if all_results:
                final_df = pd.concat(all_results).sort_values('下落率', ascending=False)
                st.session_state['top10'] = final_df.head(10)
                st.success("解析が完了しました！")

with col2:
    st.header("📈 実行ステータス")
    if st.session_state['is_running']:
        current_time = datetime.now().strftime("%H:%M")
        st.success(f"現在、自動監視が稼働中です（現在時刻: {current_time}）")
        
        # 監視ログの表示
        st.text_area("ログ", "\n".join(st.session_state['logs']), height=200)
        
        # 監視ロジック（画面が開いている間動く）
        placeholder = st.empty()
        if 'schedule' in st.session_state:
            for rid, start_t in st.session_state['schedule'].items():
                target_dt = datetime.strptime(start_t, "%H:%M") - timedelta(minutes=10)
                target_t = target_dt.strftime("%H:%M")
                
                if current_time == target_t and rid not in st.session_state['saved_odds']:
                    df = get_odds_data(rid, mode="odds")
                    if not df.empty:
                        st.session_state['saved_odds'][rid] = df
                        st.session_state['logs'].append(f"💰 {current_time}: {rid} の10分前データを取得・保存しました")
                        st.rerun()
        
        # 30秒ごとに画面を更新して監視を継続
        time.sleep(30)
        st.rerun()
    else:
        st.info("設定を確認し、「自動監視を開始する」を押してください。")

# --- 解析結果の表示 ---
if 'top10' in st.session_state:
    st.divider()
    st.header("🔥 本日の大口流入ランキング BEST10")
    df = st.session_state['top10']
    
    # メトリック表示
    m_cols = st.columns(5)
    for i, (_, row) in enumerate(df.head(5).iterrows()):
        with m_cols[i]:
            st.metric(label=f"{row['レース']} {row['馬名']}", 
                      value=f"{row['複勝_result']:.1f}", 
                      delta=f"-{row['下落率']*100:.1f}%")
    
    st.table(df[['レース', '馬名', '複勝_odds', '複勝_result', '下落率']])
