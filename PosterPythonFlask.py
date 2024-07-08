from flask import Flask, request, send_file, render_template, redirect, url_for, flash
import os
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from colorthief import ColorThief
import textwrap
import re

app = Flask(__name__)

app.secret_key = os.urandom(24)

# Spotify API credentials
CLIENT_ID = '9541df5016954307900d70df168a2d0a'
CLIENT_SECRET = '8e30826cf40d4c4cb769fe9195e12db9'

# Authentication with Spotify API
client_credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

def get_album_info(album_id):
    try:
        album = sp.album(album_id)
        album_name = album['name']
        artist_name = album['artists'][0]['name']
        release_date = album['release_date']
        cover_url = album['images'][0]['url']
        tracklist = [track['name'] for track in album['tracks']['items']]
        album_length = sum(track['duration_ms'] for track in album['tracks']['items']) // 1000  # in seconds
        return album_name, artist_name, release_date, cover_url, tracklist, album_length
    except spotipy.exceptions.SpotifyException as e:
        app.logger.error(f"Spotify API error: {e}")
        return None

def format_duration(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02}"

def wrap_text(text, font, max_width):
    """Wrap text to fit a specified width."""
    lines = []
    words = text.split()
    while words:
        line = ''
        while words and font.getbbox(line + words[0])[2] <= max_width:
            line += (words.pop(0) + ' ')
        lines.append(line.strip())
    return lines

def extract_album_id(url_or_id):
    pattern = r'(album/|si=)([a-zA-Z0-9]+)'
    match = re.search(pattern, url_or_id)
    if match:
        return match.group(2)
    return url_or_id

def create_album_poster(album_name, artist_name, release_date, cover_url, tracklist, album_length, output_path):
    # A4 dimensions in pixels at 300 DPI
    a4_width, a4_height = 2480, 3508
    
    # Download album cover
    response = requests.get(cover_url)
    cover_image = Image.open(BytesIO(response.content))
    
    """
    # Extract dominant color from cover image
    color_thief = ColorThief(BytesIO(response.content))
    dominant_color = color_thief.get_color(quality=1)
    """
    
    # Define border size and color
    border_size = 30
    border_color = 'white'
    
    # Create a blank image for the poster with the dominant color
    poster_width, poster_height = a4_width, a4_height
    poster = Image.new('RGB', (poster_width, poster_height), 'white')
    
    # Calculate dimensions for the image and text areas
    cover_image_height = int(poster_height * 2 / 3)
    text_area_height = poster_height - cover_image_height
    
    # Resize cover image to fit the top 2/3 of the poster
    cover_image = cover_image.resize((poster_width - 2 * border_size, cover_image_height - 2 * border_size))
    
    # Add border to the cover image
    cover_image_with_border = ImageOps.expand(cover_image, border=border_size, fill=border_color)
    
    # Paste the album cover with border on the poster
    poster.paste(cover_image_with_border, (0, 0))
    
    # Path to the Proxima Nova Bold font file
    font_path = "static/fonts/Proxima-Nova-Bold.ttf"
    
    # Initialize drawing context
    draw = ImageDraw.Draw(poster)
    font_title = ImageFont.truetype(font_path, 125)
    font_subtitle = ImageFont.truetype(font_path, 100)
    font_text = ImageFont.truetype("static/fonts/Proxima-Nova.otf", 60)
    
    # Calculate text positions
    text_start_y = cover_image_height + 20
    
    # Resize album title font if necessary and wrap text if it's too long
    max_title_width = poster_width - 100
    album_name_lines = wrap_text(album_name, font_title, max_title_width)
    
    if len(album_name_lines) > 2:
        # If more than 2 lines, reduce font size
        font_title = ImageFont.truetype(font_path, 100)
        album_name_lines = wrap_text(album_name, font_title, max_title_width)
    
    # Draw the album title
    current_y = text_start_y
    for line in album_name_lines[:2]:  # Limit to 2 lines
        draw.text((50, current_y), line, fill="black", font=font_title)
        current_y += font_title.getbbox(line)[3] + 10  # Line height with some padding
        
    draw.text((50, current_y), f"{artist_name}", fill="black", font=font_subtitle)
    
    # Right-aligned release date and album length
    release_date_text = f"Release Date: {release_date}"
    album_length_text = f"Album Length: {format_duration(album_length)}"
    release_date_width = draw.textbbox((0, 0), release_date_text, font=font_text)[2]
    album_length_width = draw.textbbox((0, 0), album_length_text, font=font_text)[2]
    poster_right_margin = 50

    draw.text((poster_width - release_date_width - poster_right_margin, text_start_y + 140), release_date_text, fill="black", font=font_text)
    draw.text((poster_width - album_length_width - poster_right_margin, text_start_y + 210), album_length_text, fill="black", font=font_text)
    
    # Draw the tracklist
    tracklist_start_y = current_y + 120
    draw.text((50, tracklist_start_y), "Tracklist:", fill="black", font=font_text)
    
    # Calculate max tracks per column
    if len(album_name_lines) > 1:
        tracklist_column_height = text_area_height - 500

    if len(album_name_lines) == 1:
        tracklist_column_height = text_area_height - 400
        
    line_height = font_text.getbbox("A")[3] + 15  # Height of each line with some padding
    ##max_tracks_per_column = tracklist_column_height // line_height  # Assuming each track takes one line
    max_tracks_per_column = 9
    
    num_columns = (len(tracklist) + max_tracks_per_column - 1) // max_tracks_per_column
    column_width = (poster_width-50) // num_columns

    for col in range(num_columns):
        current_y = tracklist_start_y + line_height
        for i in range(max_tracks_per_column):
            track_index = col * max_tracks_per_column + i
            if track_index >= len(tracklist):
                break
            track_name = tracklist[track_index]
            wrapped_lines = wrap_text(track_name, font_text, column_width - 100)
            draw.text((50 + col * column_width, current_y), f"{track_index + 1}. {wrapped_lines[0]}", fill="black", font=font_text)
            current_y += line_height
            for line in wrapped_lines[1:]:
                draw.text((70 + col * column_width, current_y), line, fill="black", font=font_text)
                current_y += line_height
    
    # Save the poster to a file
    poster.save(output_path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_poster', methods=['POST'])
def generate_poster():
    album_input = request.form['album_id']
    album_id = extract_album_id(album_input)

    album_info = get_album_info(album_id)
    if album_info is None:
        flash("Invalid album ID or link. Please try again.")
        return redirect(url_for('index'))
    
    album_name, artist_name, release_date, cover_url, tracklist, album_length = get_album_info(album_id)
    output_path = f'static/posters/{album_id}.png'
    create_album_poster(album_name, artist_name, release_date, cover_url, tracklist, album_length, output_path)
    
    return redirect(url_for('show_poster', poster_filename=f'{album_id}.png'))

@app.route('/poster/<poster_filename>')
def show_poster(poster_filename):
    return render_template('poster.html', poster_url=url_for('static', filename=f'posters/{poster_filename}'))

if __name__ == '__main__':
    # Ensure the posters directory exists
    if not os.path.exists('static/posters'):
        os.makedirs('static/posters')
    app.run(debug=True)


"""
good kid, m.A.A.d city: 748dZDqSZy6aPXKcI9H80u
Blonde: 3mH6qwIy9crq0I9YQbOuDf
Faces: 5SKnXCvB4fcGSZu32o3LRY
We Go Again: 4vdQXcHcAGcVSBA7956EMq
Enter The Wu-Tang: 3tQd5mwBtVyxCoEo4htGAV

https://open.spotify.com/album/5GuWww4OaildzkmTTlfMN3?si=1UGTSlb_TwuLVhOSwUS6Tg
https://open.spotify.com/album/5GuWww4OaildzkmTTlfMN3
"""
