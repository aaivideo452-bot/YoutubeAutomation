# ===== RENDER/GITHUB SERVER COMPONENT =====
# Deploy this on render.com or similar service

from flask import Flask, request, jsonify, send_file
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
import yt_dlp
import requests
import os
import tempfile
from pathlib import Path
import time
import json

app = Flask(__name__)

# Configuration
TRENDING_SONGS_API = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
TEMP_DIR = tempfile.gettempdir()

def get_trending_song():
    """Get latest trending song from YouTube Music"""
    try:
        params = {
            'part': 'snippet',
            'chart': 'mostPopular',
            'videoCategoryId': '10',  # Music category
            'maxResults': 1,
            'regionCode': 'US',
            'key': YOUTUBE_API_KEY
        }
        
        response = requests.get(TRENDING_SONGS_API, params=params)
        data = response.json()
        
        if data.get('items'):
            video_id = data['items'][0]['id']
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        print(f"Error getting trending song: {e}")
    
    # Fallback to popular songs
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Replace with actual trending

def download_youtube_audio(url, output_path):
    """Download audio from YouTube video"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path + '.mp3'
    except Exception as e:
        print(f"Error downloading audio: {e}")
        return None

def download_youtube_video(url, output_path):
    """Download video from YouTube"""
    ydl_opts = {
        'format': 'best[ext=mp4]',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None

def process_video(input_video_path, output_video_path):
    """Remove original audio and add trending song"""
    try:
        # Load video
        video = VideoFileClip(input_video_path)
        
        # Get trending song
        trending_song_url = get_trending_song()
        print(f"Using trending song: {trending_song_url}")
        
        # Download trending song audio
        audio_path = os.path.join(TEMP_DIR, f'trending_song_{int(time.time())}')
        downloaded_audio = download_youtube_audio(trending_song_url, audio_path)
        
        if not downloaded_audio or not os.path.exists(downloaded_audio):
            print("Failed to download trending song, using silent video")
            video_without_audio = video.without_audio()
            video_without_audio.write_videofile(
                output_video_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(TEMP_DIR, 'temp_audio.m4a'),
                remove_temp=True
            )
        else:
            # Load new audio
            new_audio = AudioFileClip(downloaded_audio)
            
            # Loop audio if video is longer
            if video.duration > new_audio.duration:
                loops_needed = int(video.duration / new_audio.duration) + 1
                new_audio = CompositeAudioClip([
                    new_audio.set_start(i * new_audio.duration) 
                    for i in range(loops_needed)
                ])
            
            # Trim audio to video length
            new_audio = new_audio.subclip(0, video.duration)
            
            # Remove original audio and add new audio
            video_without_audio = video.without_audio()
            final_video = video_without_audio.set_audio(new_audio)
            
            # Write output
            final_video.write_videofile(
                output_video_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(TEMP_DIR, 'temp_audio.m4a'),
                remove_temp=True
            )
            
            # Clean up
            new_audio.close()
            final_video.close()
            
            if os.path.exists(downloaded_audio):
                os.remove(downloaded_audio)
        
        video_without_audio.close()
        video.close()
        
        return True
        
    except Exception as e:
        print(f"Error processing video: {e}")
        return False

@app.route('/download', methods=['POST'])
def download_video():
    """Download video from YouTube"""
    data = request.json
    video_url = data.get('videoUrl')
    
    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400
    
    try:
        # Create temp file
        output_path = os.path.join(TEMP_DIR, f'video_{int(time.time())}.mp4')
        
        # Download video
        downloaded_path = download_youtube_video(video_url, output_path)
        
        if downloaded_path and os.path.exists(downloaded_path):
            # Return file URL (in production, upload to cloud storage)
            return jsonify({
                'success': True,
                'fileUrl': f'/get-file/{os.path.basename(downloaded_path)}'
            })
        else:
            return jsonify({'error': 'Failed to download video'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process-video', methods=['POST'])
def process_video_endpoint():
    """Process video: remove audio and add trending song"""
    data = request.json
    video_url = data.get('videoUrl')
    
    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400
    
    try:
        # Download video from URL
        input_path = os.path.join(TEMP_DIR, f'input_{int(time.time())}.mp4')
        response = requests.get(video_url, stream=True)
        
        with open(input_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Process video
        output_path = os.path.join(TEMP_DIR, f'output_{int(time.time())}.mp4')
        success = process_video(input_path, output_path)
        
        if success and os.path.exists(output_path):
            # In production, upload to cloud storage and return URL
            # For now, return local path
            return jsonify({
                'success': True,
                'processedFileUrl': f'/get-file/{os.path.basename(output_path)}'
            })
        else:
            return jsonify({'error': 'Failed to process video'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)

@app.route('/get-file/<filename>', methods=['GET'])
def get_file(filename):
    """Serve processed file"""
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='video/mp4')
    return jsonify({'error': 'File not found'}), 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)