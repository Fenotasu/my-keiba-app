import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import os

# --- ページ設定 ---
st.set_page_config(page_title="共同通信杯・リベンジ監視くん", layout="wide")

# 保存用ファイル名（日付を入れると管理しやすいです）
SAVE_FILE = f"odds_log_{datetime.now().strftime('%Y%m%d')}.csv"

# セッション状態の初期化
if 'logs' not in st.session_state: st.session_state['logs'] = []
if 'is_running' not in st.session_state: st.session_state['is_running'] = False

def get_odds_data(race_id, mode="odds"):
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
            data.append({"race_id": race_id, "馬名": name, f"複勝_{mode}": float(place)})
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def get_race_schedule(date_code, venue):
    headers = {"User-Agent": "Mozilla/5.0"}
    schedule = {}
    try:
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
st.title("🤖 【日曜リベンジ】10分前オッズ自動保存システム")
st.markdown(f"現在の保存ファイル: `{SAVE_FILE}` (Macのローカルに自動保存されます)")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("⚙️ 監視設定")
    date_input = st.text_input("開催日(8桁)", value="20260208") # 明日の日付
    venue_input = st.selectbox("会場", ["05(東京)", "08(京都)", "10(小倉)"])[:2]
    
    if st.button("🚀 監視＆ファイル保存を開始"):
        st.session_state['is_running'] = True
        st.session_state['schedule'] = get_race_schedule(date_input, venue_input)
        st.session_state['logs'].append(f"✅ {datetime.now().strftime('%H:%M')} 監視を開始")

    st.divider()
    if st.button("📊 保存ファイルから解析する"):
        if not os.path.exists(SAVE_FILE):
            st.error("まだ保存されたファイルがありません。")
        else:
            # ファイルからデータを読み込む
            saved_df = pd.read_csv(SAVE_FILE)
            all_results = []
            
            unique_races = saved_df['race_id'].unique()
            for rid in unique_races:
                # 10分前データ
                base_df = saved_df[saved_df['race_id'] == rid]
                # 今の確定データ（あるいは最新データ）を取得
                now_df = get_odds_data(rid, mode="result")
                
                if not now_df.empty:
                    merged = pd.merge(now_df, base_df, on="馬名")
                    merged['下落率'] = (merged['複勝_odds'] - merged['複勝_result']) / merged['複勝_odds']
                    merged['レース'] = f"{str(rid)[-2:]}R"
                    all_results.append(merged)
            
            if all_results:
                final_df = pd.concat(all_results).sort_values('下落率', ascending=False)
                st.session_state['top10'] = final_df.head(10)
                st.success("ファイルから解析が完了しました！")

with col2:
    st.header("📈 実行ステータス")
    if st.session_state['is_running']:
        current_time = datetime.now().strftime("%H:%M")
        st.info(f"監視稼働中... 現在時刻: {current_time}")
        
        if 'schedule' in st.session_state:
            for rid, start_t in st.session_state['schedule'].items():
                target_dt = datetime.strptime(start_t, "%H:%M") - timedelta(minutes=10)
                target_t = target_dt.strftime("%H:%M")
                
                # 10分前になったら取得＆保存
                if current_time == target_t:
                    # すでにファイルにこのレースのIDがあるかチェック
                    already_saved = False
                    if os.path.exists(SAVE_FILE):
                        temp_df = pd.read_csv(SAVE_FILE)
                        if rid in temp_df['race_id'].astype(str).values:
                            already_saved = True
                    
                    if not already_saved:
                        df = get_odds_data(rid, mode="odds")
                        if not df.empty:
                            # ファイルに追記保存
                            df.to_csv(SAVE_FILE, mode='a', index=False, header=not os.path.exists(SAVE_FILE))
                            st.session_state['logs'].append(f"💾 {current_time}: {rid} をファイルに保存！")
                            st.rerun()
        
        st.text_area("ログ（履歴）", "\n".join(st.session_state['logs']), height=200)
        time.sleep(30)
        st.rerun()

# 結果表示
if 'top10' in st.session_state:
    st.divider()
    st.header("🔥 本日の大口下落ランキング (CSV集計)")
    st.dataframe(st.session_state['top10'][['レース', '馬名', '複勝_odds', '複勝_result', '下落率']])
