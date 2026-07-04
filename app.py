from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

app = Flask(__name__)
CORS(app)

TEAMS_FILE = 'teams.json'
MATCHES_FILE = 'matches.json'
NEWS_FILE = 'news.json'
PLAYERS_FILE = 'players.json'

UPLOAD_CSVS = 'static/csvs'
UPLOAD_IMAGES = 'static/images'
os.makedirs(UPLOAD_CSVS, exist_ok=True)
os.makedirs(UPLOAD_IMAGES, exist_ok=True)

def read_json(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return []

def write_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def process_tactical_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        required_columns = ['Player', 'Min', 'Points', 'Steals', 'Rebounds', 'Blocks', 'AST', 'FGA', 'FGM', 'FTA', 'FTM', 'TO']
        if all(col in df.columns for col in required_columns):
            df['EFF'] = (df['Points'] + df['Rebounds'] + df['AST'] + df['Steals'] + df['Blocks']) - \
                        ((df['FGA'] - df['FGM']) + (df['FTA'] - df['FTM']) + df['TO'])
            c_min = df['Min'].mean()
            c_pts = df['Points'].mean()
            c_blk = df['Blocks'].mean()
            df['Distance_From_Centroid'] = np.sqrt((df['Min'] - c_min)**2 + (df['Points'] - c_pts)**2 + (df['Blocks'] - c_blk)**2)
            df.to_csv(file_path, index=False)
            return True
    except Exception as e:
        print(f"Error processing tactical CSV: {e}")
    return False

@app.route('/')
def admin_home():
    return render_template('index.html')

# --- NEW: GENERATE PLOTLY VISUALS FROM UPLOADED MATCH CSV ---
@app.route('/api/matches/<int:match_id>/visuals')
def generate_match_visuals(match_id):
    matches = read_json(MATCHES_FILE)
    match = next((m for m in matches if int(m.get('id')) == match_id), None)
    
    if not match or not match.get('csv_file1'):
        return "<h3>No CSV data available for this match yet. Please upload Team 1 CSV.</h3>", 404
    
    csv_path = os.path.join(UPLOAD_CSVS, match['csv_file1'])
    if not os.path.exists(csv_path):
        return f"<h3>CSV file not found on server.</h3>", 404

    # 1. Read Data dynamically from uploaded CSV
    df = pd.read_csv(csv_path)
    metrics_list = ['Min', 'Points', 'Steals', 'Rebounds', 'Blocks']
    
    # Recalculate EFF & Centroids if not set
    if 'EFF' not in df.columns:
        df['EFF'] = (df['Points'] + df['Rebounds'] + df['AST'] + df['Steals'] + df['Blocks']) - \
                    ((df['FGA'] - df['FGM']) + (df['FTA'] - df['FTM']) + df['TO'])

    # --- 1. Tactical Network Chart ---
    m_x, m_y = [1]*5, [2, 5, 8, 11, 14]
    pl_x, pl_y = [2.5]*len(df), list(np.linspace(1, 15, len(df)))
    fig_net = go.Figure()
    
    main_nodes_hover = []
    for m in metrics_list:
        leader_name = df.loc[df[m].idxmax(), 'Player']
        leader_val = df[m].max()
        avg_val = df[m].mean()
        main_nodes_hover.append(f"<b>Metric: {m}</b><br>Team Avg: {avg_val:.1f}<br>Leader: {leader_name} ({leader_val})")

    for m_idx, m_name in enumerate(metrics_list):
        x_lines, y_lines = [], []
        for idx, row in df.iterrows():
            x_lines.extend([1, 2.5, None])
            y_lines.extend([m_y[m_idx], pl_y[idx], None])
            
        fig_net.add_trace(go.Scatter(
            x=x_lines, y=y_lines, mode='lines',
            line=dict(color='orange', width=1.8), opacity=0.12, hoverinfo='skip'
        ))
        fig_net.add_trace(go.Scatter(
            x=pl_x, y=pl_y, mode='markers',
            marker=dict(
                size=df[m_name] * (1.8 if m_name=='Min' else 4.5) + 8,
                color=df[m_name], colorscale='Oranges',
                showscale=True if m_name == 'Points' else False,
                colorbar=dict(title="Stat Scale", thickness=15, x=1.12) if m_name == 'Points' else None,
            ),
            name=m_name, hoverinfo='text',
            hovertext=[f"Player: {p}<br>{m_name}: {val}" for p, val in zip(df['Player'], df[m_name])]
        ))

    fig_net.add_trace(go.Scatter(x=m_x, y=m_y, mode='markers+text', marker=dict(size=24, color='white', line=dict(color='orange', width=2.5)), text=metrics_list, textposition="middle left", hoverinfo='text', hovertext=main_nodes_hover, showlegend=False))
    fig_net.add_trace(go.Scatter(x=pl_x, y=pl_y, mode='text', text=df['Player'], textposition="middle right", hoverinfo='skip', showlegend=False))
    
    buttons = [dict(label="Show All Connections", method="update", args=[{"visible": [True] * (2 * len(metrics_list)) + [True, True]}])]
    for i, m_name in enumerate(metrics_list):
        visibility = [False] * (2 * len(metrics_list)) + [True, True]
        visibility[2 * i], visibility[2 * i + 1] = True, True
        buttons.append(dict(label=f"Focus on: {m_name}", method="update", args=[{"visible": visibility}]))
        
    fig_net.update_layout(title=f"🔗 Tactical Network - {match['title']}", template="plotly_dark", showlegend=False, xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.3, 4.3]), yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0, 16]), updatemenus=[dict(buttons=buttons, direction="down", showactive=True, x=0.4, y=1.15, bgcolor="#222222")])

    # --- 2. Heatmap Chart ---
    fig_heat = px.imshow(df[metrics_list].values, x=metrics_list, y=df['Player'], color_continuous_scale="Oranges", text_auto='.1f', title="🏀 Player Statistics Heatmap")
    fig_heat.update_traces(xgap=4, ygap=4)
    fig_heat.update_layout(template="plotly_dark")

    # --- 3. 3D Performance Scout ---
    x_stat, y_stat, z_stat = df['Min'], df['Points'], df['Blocks']
    c_x, c_y, c_z = x_stat.mean(), y_stat.mean(), z_stat.mean()
    stat_distances = np.sqrt((x_stat - c_x)**2 + (y_stat - c_y)**2 + (z_stat - c_z)**2)
    closest_stat_idx, farthest_stat_idx = stat_distances.idxmin(), stat_distances.idxmax()

    fig_3d = go.Figure()
    fig_3d.add_trace(go.Scatter3d(x=x_stat, y=y_stat, z=z_stat, mode='markers+text', marker=dict(size=df['Points']*2 + 6, color=df['Points'], colorscale='Oranges', opacity=0.8), text=df['Player'], textposition="top center", name="Players"))
    fig_3d.add_trace(go.Scatter3d(x=[c_x], y=[c_y], z=[c_z], mode='markers', marker=dict(size=16, color='red', line=dict(color='white', width=3)), name='Team Centroid'))
    fig_3d.update_layout(
        title="🌐 3D Performance Scout - Minutes vs Points vs Blocks", template="plotly_dark",
        scene=dict(
            xaxis=dict(title="Minutes (Min)"), yaxis=dict(title="Points (PTS)"), zaxis=dict(title="Blocks (BLK)"),
            annotations=[
                dict(x=x_stat[closest_stat_idx], y=y_stat[closest_stat_idx], z=z_stat[closest_stat_idx], text=f"Hotspot Comfort Zone: {df.loc[closest_stat_idx, 'Player']}", showarrow=True, arrowcolor="cyan", bgcolor="black", font=dict(color="cyan")),
                dict(x=x_stat[farthest_stat_idx], y=y_stat[farthest_stat_idx], z=z_stat[farthest_stat_idx], text=f"Tactical Outlier: {df.loc[farthest_stat_idx, 'Player']}", showarrow=True, arrowcolor="magenta", bgcolor="black", font=dict(color="magenta"))
            ]
        )
    )

    # --- 4. EFF Leaderboard ---
    df_sorted = df.sort_values(by='EFF', ascending=True)
    fig_eff = px.bar(df_sorted, x='EFF', y='Player', orientation='h', color='EFF', color_continuous_scale="Oranges", text_auto='.1f', title="📊 Player Efficiency Rating (EFF) Leaderboard")
    fig_eff.update_layout(template="plotly_dark", xaxis=dict(title="EFF Score"), yaxis=dict(title="Players"))

    # Convert all figures to HTML chunks
    html_content = f"""
    <html>
    <head><title>Visual Insights - {match['title']}</title><body style="background-color:#121212; color:white; font-family:sans-serif; padding:20px;"></head>
    <h2>📊 Match Analytics Dashboard: {match['title']}</h2>
    <div style="margin-bottom:40px;">{fig_net.to_html(full_html=False, include_plotlyjs='cdn')}</div>
    <div style="margin-bottom:40px;">{fig_heat.to_html(full_html=False, include_plotlyjs=False)}</div>
    <div style="margin-bottom:40px;">{fig_3d.to_html(full_html=False, include_plotlyjs=False)}</div>
    <div style="margin-bottom:40px;">{fig_eff.to_html(full_html=False, include_plotlyjs=False)}</div>
    </body>
    </html>
    """
    return html_content

# --- TEAMS API ---
@app.route('/api/teams', methods=['GET', 'POST'])
def handle_teams():
    teams = read_json(TEAMS_FILE)
    if request.method == 'POST':
        data = request.json
        if not data or not data.get('name'):
            return jsonify({"error": "Missing name"}), 400
        new_team = {
            "id": len(teams) + 1,
            "name": data.get('name').strip(),
            "category": data.get('category', 'First Team')
        }
        teams.append(new_team)
        write_json(TEAMS_FILE, teams)
        return jsonify({"message": "Saved successfully", "id": new_team["id"]}), 201
    return jsonify(teams)

@app.route('/api/teams/<int:item_id>', methods=['DELETE'])
def delete_team(item_id):
    teams = read_json(TEAMS_FILE)
    write_json(TEAMS_FILE, [t for t in teams if int(t.get('id')) != item_id])
    return jsonify({"message": "Deleted successfully"})

# --- PLAYERS API ---
@app.route('/api/players', methods=['GET', 'POST'])
def handle_players():
    players = read_json(PLAYERS_FILE)
    if request.method == 'POST':
        name = request.form.get('name')
        number = request.form.get('number')
        position = request.form.get('position')
        team_id = request.form.get('team_id')
        if not name or not number or not position or not team_id:
            return jsonify({"error": "Missing fields"}), 400
        img_filename = ""
        if 'player_img' in request.files:
            file = request.files['player_img']
            if file and file.filename != '':
                img_filename = file.filename
                file.save(os.path.join(UPLOAD_IMAGES, img_filename))
        new_player = {
            "id": len(players) + 1,
            "name": name.strip(),
            "number": number.strip(),
            "position": position.strip(),
            "team_id": int(team_id),
            "image": img_filename
        }
        players.append(new_player)
        write_json(PLAYERS_FILE, players)
        return jsonify({"message": "Saved successfully"}), 201
    return jsonify(players)

@app.route('/api/players/<int:item_id>', methods=['DELETE'])
def delete_player(item_id):
    players = read_json(PLAYERS_FILE)
    write_json(PLAYERS_FILE, [p for p in players if int(p.get('id')) != item_id])
    return jsonify({"message": "Deleted successfully"})

# --- MATCHES API ---
@app.route('/api/matches', methods=['GET', 'POST'])
def handle_matches():
    matches = read_json(MATCHES_FILE)
    if request.method == 'POST':
        title = request.form.get('title')
        team1 = request.form.get('team1')
        team2 = request.form.get('team2')
        primary_color = request.form.get('primary_color', '#ff6600')
        secondary_color = request.form.get('secondary_color', '#0066cc')
        match_video = request.form.get('match_video', '')
        highlights = request.form.get('highlights', '')
        if not title or not team1 or not team2:
            return jsonify({"error": "Missing fields"}), 400
        banner_filename = ""
        if 'match_banner' in request.files:
            b_file = request.files['match_banner']
            if b_file and b_file.filename != '':
                banner_filename = b_file.filename
                b_file.save(os.path.join(UPLOAD_IMAGES, banner_filename))
        csv1_filename = ""
        csv2_filename = ""
        if 'match_csv1' in request.files:
            file1 = request.files['match_csv1']
            if file1 and file1.filename != '':
                csv1_filename = file1.filename
                full_path1 = os.path.join(UPLOAD_CSVS, csv1_filename)
                file1.save(full_path1)
                process_tactical_csv(full_path1)
        if 'match_csv2' in request.files:
            file2 = request.files['match_csv2']
            if file2 and file2.filename != '':
                csv2_filename = file2.filename
                full_path2 = os.path.join(UPLOAD_CSVS, csv2_filename)
                file2.save(full_path2)
                process_tactical_csv(full_path2)
        new_match = {
            "id": len(matches) + 1,
            "title": title.strip(),
            "name": title.strip(),
            "banner": banner_filename,
            "team1": team1.strip(),
            "team2": team2.strip(),
            "primary_color": primary_color.strip(),
            "secondary_color": secondary_color.strip(),
            "csv_file1": csv1_filename,
            "csv_file2": csv2_filename,
            "match_video": match_video.strip(),
            "highlights": highlights.strip()
        }
        matches.append(new_match)
        write_json(MATCHES_FILE, matches)
        return jsonify({"message": "Saved successfully"}), 201
    return jsonify(matches)

@app.route('/api/matches/<int:item_id>', methods=['DELETE'])
def delete_match(item_id):
    matches = read_json(MATCHES_FILE)
    write_json(MATCHES_FILE, [m for m in matches if int(m.get('id')) != item_id])
    return jsonify({"message": "Deleted successfully"})

# --- NEWS API ---
@app.route('/api/news', methods=['GET', 'POST'])
def handle_news():
    news = read_json(NEWS_FILE)
    if request.method == 'POST':
        data = request.json
        if not data or not data.get('title') or not data.get('content'):
            return jsonify({"error": "Cannot be added"}), 400
        news_date = data.get('date') if data.get('date') else datetime.now().strftime('%Y-%m-%d')
        new_story = {
            "id": len(news) + 1,
            "title": data.get('title').strip(),
            "content": data.get('content').strip(),
            "image": data.get('image', '').strip(),  
            "video": data.get('video', '').strip(),
            "date": news_date
        }
        news.append(new_story)
        write_json(NEWS_FILE, news)
        return jsonify({"message": "Saved successfully"}), 201
    return jsonify(news)

@app.route('/api/news/<int:item_id>', methods=['DELETE'])
def delete_news(item_id):
    news = read_json(NEWS_FILE)
    write_json(NEWS_FILE, [n for n in news if int(n.get('id')) != item_id])
    return jsonify({"message": "Deleted successfully"})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)