import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta, timezone
import os

# 日本時間の設定
JST = timezone(timedelta(hours=+9), 'JST')

st.set_page_config(page_title="日本時間対応・監視くん", layout="wide")

# ファイル名も日本時間で生成
current_date_jst = datetime.now(JST).strftime('%Y%m%d')
SAVE_FILE = f"odds_log_{current_date_jst}.csv"

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

st.title("🤖 【日本時間・修正版】10分前監視システム")
if st.button("🧪 【テスト】今すぐ現在のオッズを保存してみる"):
    # 現在時刻に関係なく、直近のレース（例: 9Rなど）として保存
    test_rid = f"{date_input}{venue_input}09" 
    df = get_odds_data(test_rid, mode="odds")
    if not df.empty:
        df.to_csv(SAVE_FILE, mode='a', index=False, header=not os.path.exists(SAVE_FILE))
        st.success(f"テスト保存成功！ファイル `{SAVE_FILE}` が作成されました。")
        st.rerun()
st.write(f"現在時刻 (日本): {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}")

col1, col2 = st.columns([1, 2])

with col1:
    date_input = st.text_input("開催日(8桁)", value=current_date_jst)
    venue_input = st.selectbox("会場", ["05(東京)", "08(京都)", "10(小倉)"])[:2]

# venue_input = ... のすぐ下に貼り付け
    if st.button("🧪 【テスト】今すぐ現在のオッズを保存してみる"):
        test_rid = f"{date_input}{venue_input}09" 
        df = get_odds_data(test_rid, mode="odds")
        if not df.empty:
            df.to_csv(SAVE_FILE, mode='a', index=False, header=not os.path.exists(SAVE_FILE))
            st.success(f"テスト保存成功！ファイル `{SAVE_FILE}` が作成されました。")
            st.rerun()
    if st.button("🚀 日本時間で監視を開始"):
        st.session_state['is_running'] = True
        st.session_state['schedule'] = get_race_schedule(date_input, venue_input)
        st.session_state['logs'].append(f"✅ {datetime.now(JST).strftime('%H:%M')} 監視スタート")

    if st.button("📊 保存ファイルから解析"):
        if not os.path.exists(SAVE_FILE):
            st.error("保存ファイルが見つかりません。取得までお待ちください。")
        else:
            saved_df = pd.read_csv(SAVE_FILE)
            all_results = []
            for rid in saved_df['race_id'].unique():
                base_df = saved_df[saved_df['race_id'] == rid]
                now_df = get_odds_data(rid, mode="result")
                if not now_df.empty:
                    merged = pd.merge(now_df, base_df, on="馬名")
                    merged['下落率'] = (merged['複勝_odds'] - merged['複勝_result']) / merged['複勝_odds']
                    merged['レース'] = f"{str(rid)[-2:]}R"
                    all_results.append(merged)
            if all_results:
                st.session_state['top10'] = pd.concat(all_results).sort_values('下落率', ascending=False).head(10)
                st.success("解析完了")

with col2:
    if st.session_state['is_running']:
        current_time_jst = datetime.now(JST).strftime("%H:%M")
        st.info(f"監視中... 現在時刻: {current_time_jst}")
        
        if 'schedule' in st.session_state:
            for rid, start_t in st.session_state['schedule'].items():
                target_dt = datetime.strptime(start_t, "%H:%M") - timedelta(minutes=10)
                target_t = target_dt.strftime("%H:%M")
                
                # 日本時間で比較
                if current_time_jst == target_t:
                    # 重複チェック省略して取得・保存
                    df = get_odds_data(rid, mode="odds")
                    if not df.empty:
                        df.to_csv(SAVE_FILE, mode='a', index=False, header=not os.path.exists(SAVE_FILE))
                        st.session_state['logs'].append(f"💾 {current_time_jst}: {rid} 保存完了")
                        st.rerun()
        
        st.text_area("ログ", "\n".join(st.session_state['logs']), height=200)
        time.sleep(30)
        st.rerun()
