from flask import Flask, request, jsonify, session, render_template, send_from_directory
import os
import yt_dlp
from flask_sqlalchemy import SQLAlchemy
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 실제 환경에서는 안전한 키를 설정해야 합니다.

# SQLite 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 오디오 저장 폴더 경로 설정
AUDIO_FOLDER = 'audio'
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

db = SQLAlchemy(app)

# User 모델 정의
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Playlist 모델 정의
class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    songs = db.Column(db.Text, nullable=True)  # JSON 형태로 저장될 곡 목록

# 애플리케이션 컨텍스트 내에서 데이터베이스 및 테이블 생성
with app.app_context():
    db.create_all()  # 데이터베이스 및 테이블 생성

# 홈 페이지 (HTML 제공)
@app.route('/')
def home():
    return render_template('index.html')

# 사용자 등록
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '이미 존재하는 사용자 이름입니다.'}), 400

    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '회원가입 성공!'})

# 로그인
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username, password=password).first()
    
    if user:
        session['user_id'] = user.id
        return jsonify({'message': '로그인 성공!'})
    else:
        return jsonify({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}), 401

# 오디오 다운로드 및 플레이리스트에 추가
@app.route('/convert', methods=['POST'])
def convert_audio():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 403

    url = request.json.get('url')
    playlist_name = request.json.get('playlist_name')
    custom_name = request.json.get('audio_name')

    if not playlist_name:
        return jsonify({'error': '플레이리스트 이름을 입력하세요.'}), 400
    if not custom_name:
        return jsonify({'error': '파일 이름을 입력하세요.'}), 400

    # 사용자 맞춤 파일 이름 설정
    output_file_path = os.path.join(AUDIO_FOLDER, f'{custom_name}')

    # 파일이 이미 존재하는지 확인
    if os.path.exists(output_file_path):
        return jsonify({'error': '파일이 이미 존재합니다. 다른 이름을 사용해 주세요.'}), 400

    # yt-dlp 옵션 설정
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_file_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',  # 비트레이트를 320kbps로 최적화
        }],
    }

    # 다운로드 수행
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return jsonify({'error': f'다운로드 오류: {str(e)}'}), 500

    # 플레이리스트 가져오기
    playlist = Playlist.query.filter_by(user_id=session['user_id'], name=playlist_name).first()

    if playlist is None:
        # 플레이리스트가 없으면 새로 생성 (songs를 빈 리스트로 초기화)
        playlist = Playlist(user_id=session['user_id'], name=playlist_name, songs=json.dumps([]))
        db.session.add(playlist)
        db.session.commit()

    # 곡 목록 업데이트
    try:
        songs = json.loads(playlist.songs) if playlist.songs else []
    except json.JSONDecodeError:
        songs = []  # JSON 형식이 아닐 경우 빈 리스트로 초기화

    songs.append(f'{custom_name}.mp3')
    playlist.songs = json.dumps(songs)
    db.session.commit()

    return jsonify({'message': '다운로드 완료!', 'filename': f'{custom_name}.mp3'})

# 플레이리스트 목록 반환
@app.route('/playlists', methods=['GET'])
def get_playlists():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 403

    playlists = Playlist.query.filter_by(user_id=session['user_id']).all()
    result = {}

    for p in playlists:
        try:
            result[p.name] = json.loads(p.songs) if p.songs else []
        except json.JSONDecodeError:
            result[p.name] = []  # JSON이 유효하지 않은 경우 빈 리스트 설정

    return jsonify(result)

# 오디오 파일 제공
@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)
