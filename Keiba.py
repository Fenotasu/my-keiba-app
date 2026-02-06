import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
from bs4 import BeautifulSoup

# --- ページ設定 ---
st.set_page_config(page_title="競馬大口流入・異常検知ツール", layout="wide")

# --- データ取得関数（ハイブリッド版） ---
def get_real_odds(race_id):
    urls = [
        f"https://race.netkeiba.com/race/odds.html?race_id={race_id}",
        f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('tr.HorseList') 
            if not rows: continue

            data = []
            for row in rows:
                name_tag = row.select_one('.HorseName') or row.select_one('.Horse_Name')
                win_tag = row.select_one('.WinOdds') or row.select_one('.Odds')
                place_tag = row.select_one('.PlaceOdds')
                
                if not name_tag or not win_tag: continue
                
                name = name_tag.text.strip()
                win_val = win_tag.text.strip().replace('---', '0').replace('取消', '0')
                
                if place_tag and '-' in place_tag.text:
                    place_val = place_tag.text.split('-')[0].strip()
                else:
                    # 複勝データがない場合は単勝の25%で仮計算
                    place_val = str(round(float(win_val) * 0.25, 1)) if win_val.replace('.','').isdigit() else "0.0"

                try:
                    win_f = float(win_val)
                    place_f = float(place_val)
                    if win_f <= 0: continue
                except: continue

                data.append({"馬名": name, "単勝オッズ": win_f, "複勝オッズ": place_f})
            if data: return pd.DataFrame(data)
        except: continue
    return pd.DataFrame()

# --- メイン画面 ---
st.title("🏇 直前大口流入・異常検知アラート")
st.markdown("締め切り10分前と現在のオッズを比較し、プロの資金が入った馬を特定します。")

# サイドバー
st.sidebar.header("1. レース選択")
race_id = st.sidebar.text_input("Race ID (12桁)", value="202608020211")

if st.sidebar.button("最新データを取得"):
    df_now = get_real_odds(race_id)
    if not df_now.empty:
        st.session_state['df'] = df_now
        st.sidebar.success("データを更新しました")
    else:
        st.sidebar.error("取得失敗")

st.sidebar.divider()
st.sidebar.header("2. 比較基準の設定")
if st.sidebar.button("今のオッズを「10分前」として保存"):
    if 'df' in st.session_state:
        st.session_state['base_df'] = st.session_state['df']
        st.session_state['base_time'] = pd.Timestamp.now().strftime('%H:%M:%S')
        st.sidebar.info(f"基準時刻: {st.session_state['base_time']}")

# --- 比較・分析表示 ---
if 'df' in st.session_state:
    df = st.session_state['df']
    
    if 'base_df' in st.session_state:
        # マージして比較
        diff_df = pd.merge(
            df[['馬名', '複勝オッズ']], 
            st.session_state['base_df'][['馬名', '複勝オッズ']], 
            on='馬名', suffixes=('_今', '_前')
        )
        # 下落率計算
        diff_df['下落率'] = (diff_df['複勝オッズ_前'] - diff_df['複勝オッズ_今']) / diff_df['複勝オッズ_前']
        
        # 🚨 異常検知アラート (下落率10%以上を表示)
        st.subheader(f"🔍 {st.session_state['base_time']} からの変化")
        abnormal = diff_df[diff_df['下落率'] >= 0.10].sort_values('下落率', ascending=False)

        if not abnormal.empty:
            cols = st.columns(len(abnormal) if len(abnormal) < 4 else 4)
            for i, (_, row) in enumerate(abnormal.iterrows()):
                with cols[i % 4]:
                    st.metric(
                        label=f"🔥 大口流入: {row['馬名']}",
                        value=f"複勝 {row['複勝オッズ_今']:.1f}",
                        delta=f"-{row['下落率']*100:.1f}%",
                        delta_color="inverse"
                    )
            
            st.divider()
            # 視覚的なグラフ
            fig = px.bar(diff_df.sort_values('下落率'), x='下落率', y='馬名', orientation='h',
                         title="オッズ急落率（右に長いほど買われている）",
                         color='下落率', color_continuous_scale='Reds')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("現在、10分前と比較して大きなオッズの動き（10%以上の急落）はありません。")
    
    # 全馬のデータ一覧
    with st.expander("全馬の現在データを見る"):
        st.dataframe(df)
else:
    st.warning("左のボタンから「最新データを取得」してください。")
