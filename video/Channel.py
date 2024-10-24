from flask import Flask, render_template, jsonify, request
from googleapiclient.discovery import build
from textblob import TextBlob
import requests

app = Flask(__name__)

# Replace with your API key and valid Gemini endpoint
API_KEY = 'AIzaSyArRbf0nKGuiDaJm8MJCIMaDEf_SVITz0o'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=AIzaSyA8SASB1-aeG5T7Pt6tiRIWZWPCcwm-iPo'  # Replace with actual Gemini API URL

# YouTube Channel Information Function
def get_channel_info(channel_id):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.channels().list(
        part='snippet,statistics,brandingSettings',
        id=channel_id
    )
    response = request.execute()

    if 'items' in response:
        channel = response['items'][0]
        channel_name = channel['snippet']['title']
        channel_logo_url = channel['snippet']['thumbnails']['high']['url']
        subscriber_count = channel['statistics']['subscriberCount']
        banner_url = channel['brandingSettings']['image'].get('bannerExternalUrl', channel['snippet']['thumbnails']['high']['url'])
        return channel_name, channel_logo_url, subscriber_count, banner_url
    else:
        return None, None, None, None

@app.route('/channel_info/<channel_id>')
def channel_info(channel_id):
    name, logo_url, subscribers, banner_url = get_channel_info(channel_id)
    if name and logo_url and subscribers and banner_url:
        return jsonify({
            'channel_name': name,
            'channel_logo_url': logo_url,
            'subscriber_count': subscribers,
            'banner_url': banner_url
        })
    else:
        return jsonify({'error': 'Channel information not found'}), 404
    
@app.route('/channel_videos/<channel_id>')
def channel_videos(channel_id):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.search().list(
        part='snippet',
        channelId=channel_id,
        maxResults=50,  # or however many videos you want to fetch
        order='date'  # sorts by upload date
    )
    response = request.execute()

    videos = []
    for item in response.get('items', []):
        video_id = item['id'].get('videoId')
        if video_id:
            video_title = item['snippet']['title']
            video_thumbnail = item['snippet']['thumbnails']['high']['url']
            video_duration = 'N/A'  # Duration might need another API call
            video_views = 'N/A'  # Views also might require another call
            
            videos.append({
                'id': video_id,
                'title': video_title,
                'thumbnail': video_thumbnail,
                'duration': video_duration,
                'views': video_views
            })

    return jsonify(videos)


@app.route('/video_details/<video_id>')
def video_details(video_id):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    request = youtube.videos().list(
        part='snippet,contentDetails,statistics',
        id=video_id
    )
    response = request.execute()

    if 'items' in response and response['items']:
        video = response['items'][0]
        video_title = video['snippet']['title']
        video_description = video['snippet']['description']
        video_thumbnail = video['snippet']['thumbnails']['high']['url']
        video_duration = video['contentDetails'].get('duration', 'N/A')
        
        # Validate views and likes
        video_views = video['statistics'].get('viewCount', 'N/A') if video['statistics'].get('viewCount') is not None else '0'
        video_likes = video['statistics'].get('likeCount', 'N/A') if video['statistics'].get('likeCount') is not None else '0'

        return jsonify({
            'title': video_title,
            'description': video_description,
            'thumbnail': video_thumbnail,
            'duration': video_duration,
            'views': video_views,
            'likes': video_likes
        })
    else:
        return jsonify({'error': 'Video details not found'}), 404


# Sentiment Analysis Function
def analyze_sentiment(text):
    analysis = TextBlob(text)
    return analysis.sentiment.polarity

# YouTube Video Sentiment Analysis
@app.route('/video_sentiment/<video_id>')
def video_sentiment(video_id):
    if video_id == 'undefined':
        return jsonify({'error': 'Invalid video ID'}), 400

    youtube = build('youtube', 'v3', developerKey=API_KEY)
    
    sentiments = {'Positive': 0, 'Neutral': 0, 'Negative': 0}

    next_page_token = None

    while True:
        request = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token
        )
        response = request.execute()

        for item in response.get('items', []):
            comment = item['snippet']['topLevelComment']
            comment_text = comment['snippet']['textDisplay']
            sentiment_score = analyze_sentiment(comment_text)

            if sentiment_score > 0:
                sentiments['Positive'] += 1
            elif sentiment_score < 0:
                sentiments['Negative'] += 1
            else:
                sentiments['Neutral'] += 1

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    return jsonify(sentiments)
@app.route('/ai_analysis/<video_id>')
def ai_analysis(video_id):
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    
    try:
        video_request = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            id=video_id
        )
        video_response = video_request.execute()
    except Exception as e:
        print(f"YouTube API Error: {e}")
        return jsonify({'error': f'YouTube API error: {str(e)}'}), 500

    if 'items' not in video_response or not video_response['items']:
        return jsonify({'error': 'Video not found'}), 404

    video_data = video_response['items'][0]
    video_title = video_data['snippet']['title']
    video_description = video_data['snippet']['description']
    video_views = video_data['statistics'].get('viewCount', 'N/A')
    video_likes = video_data['statistics'].get('likeCount', 'N/A')

    # Get sentiment analysis
    sentiment_response = video_sentiment(video_id).get_json()
    if 'error' in sentiment_response:
        print("Sentiment analysis error")
        return jsonify(sentiment_response), 500

    # Prepare payload for Gemini API
    gemini_payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Provide insights for the following video:\nTitle: {video_title}\nDescription: {video_description}\nViews: {video_views}\nLikes: {video_likes}\nSentiment Analysis: Positive: {sentiment_response['Positive']}, Neutral: {sentiment_response['Neutral']}, Negative: {sentiment_response['Negative']}."
                    }
                ]
            }
        ]
    }

    # Call Gemini API
    try:
        gemini_response = requests.post(GEMINI_API_URL, json=gemini_payload)
        gemini_response.raise_for_status()  # Check for HTTP errors
        # Convert response to JSON
        gemini_data = gemini_response.json()  # This converts the Response object to a dictionary
        print(gemini_response.status_code)  # For debugging
    except requests.exceptions.RequestException as e:
        print(f"Gemini API Error: {e}")
        return jsonify({'error': f'Gemini API error: {str(e)}'}), 500

    # Now access the JSON data
    analysis_text = gemini_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
    print(analysis_text)

    return jsonify({'analysis': analysis_text})



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/analysis', methods=['GET'])
def analysis():
    channel_id = request.args.get('channel_id')
    if not channel_id:
        return jsonify({'error': 'Missing channel_id parameter'}), 400
    channel_id = request.args.get('channel_id')
    video_id = request.args.get('video_id')
    if channel_id and video_id:
        return render_template('analysis.html', channel_id=channel_id, video_id=video_id)
    else:
        return jsonify({'error': 'Channel ID or Video ID missing'}), 400

if __name__ == '__main__':
    app.run(debug=True)
