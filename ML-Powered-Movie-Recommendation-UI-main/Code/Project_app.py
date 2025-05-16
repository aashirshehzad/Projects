import streamlit as st
import pickle
import requests
import random
# Set page configuration as the first Streamlit command
st.set_page_config(
    page_title="Movie Recommendation System Using ML",
    page_icon="logo.png",
    layout="wide",
)
st.header('MOVIE RECOMMENDATION SYSTEM', divider='rainbow')

# Define the footer HTML and CSS for styling
footer = """
<style>
    .footer p {
    position: fixed;
    margin:0;
    padding:0;
    left: 0;
    bottom: 0;
    width: 100%;
    background-image: linear-gradient(90deg,orange,yellow);
    text-align: center;
    color: white;
    }
</style>

<div class="footer">
    <p>Developed by Team Itihaad</p>
</div>
"""
st.markdown(footer, unsafe_allow_html=True)

# Function to fetch movie poster URL from the TMDB API
def fetch_poster(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key=8bb921015d2d20ee4b1b630ac130a216&language=en-US"
    try:
        data = requests.get(url).json()
        poster_path = data.get("poster_path")
        if poster_path:
            full_path = f"http://image.tmdb.org/t/p/w500{poster_path}"
            return full_path
        else:
            return "https://via.placeholder.com/500x750?text=No+Image+Available"
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching poster: {e}")
        return "https://via.placeholder.com/500x750?text=No+Image+Available"

# Function to recommend movies based on a selected movie using similarity matrix
def recommend(movie):
    try:
        index = movies[movies["title"] == movie].index[0]
    except IndexError:
        st.error("Selected movie not found in the dataset.")
        return [], [], []
    
    distances = sorted(
        list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1]
    )
    recommended_movies_name = []
    recommended_movies_poster = []
    recommended_movies_id = []
    for i in distances[1:6]:  # Get top 5 recommendations excluding the selected movie
        movie_id = movies.iloc[i[0]]["movie_id"]
        recommended_movies_poster.append(fetch_poster(movie_id))
        recommended_movies_name.append(movies.iloc[i[0]]["title"])
        recommended_movies_id.append(movies.iloc[i[0]]["movie_id"])

    return recommended_movies_name, recommended_movies_poster, recommended_movies_id

# Function to recommend movies directed by the same director
def recommend_Dir(movie):
    try:
        index = director[director['title'] == movie].index[0]
    except IndexError:
        st.error("Selected movie not found in the director dataset.")
        return [], [], []
    
    L = []
    recommended_movies_name = []
    recommended_movies_poster = []
    recommended_movies_id = []
    
    for i in director.index:
        if director.loc[i, "crew"] == director.loc[index, "crew"] and director.loc[i, "title"] != director.loc[index, "title"]:
            L.append(i)
    
    if len(L) > 5:
        L = random.sample(L, 5)
    
    for i in L:
        recommended_movies_name.append(director.loc[i, 'title'])
        recommended_movies_poster.append(fetch_poster(director.loc[i, 'movie_id']))
        recommended_movies_id.append(director.loc[i, 'movie_id'])
    
    return recommended_movies_name, recommended_movies_poster, recommended_movies_id

# Function to recommend movies featuring the same main actor
def recommend_with_cast(movie):
    try:
        actor = cast_df[cast_df["title"] == movie]["cast"].iloc[0][0]
    except IndexError:
        st.error("Selected movie not found in the cast dataset.")
        return [], [], []
    
    L = []
    recommended_movies_name = []
    recommended_movies_poster = []
    recommended_movies_id = []

    for index, row in cast_df.iterrows():
        if actor in row["cast"] and row["title"] != movie:
            L.append(row)
    
    if len(L) > 5:
        L = random.sample(L, 5)
    
    for row in L:
        recommended_movies_id.append(row["movie_id"])
        recommended_movies_poster.append(fetch_poster(row["movie_id"]))
        recommended_movies_name.append(row["title"])
    
    return recommended_movies_name, recommended_movies_poster, recommended_movies_id

# Function to recommend movies of the same genre
def recommend_genres(movie):
    try:
        index = Genres[movies['title'] == movie].index[0]
    except IndexError:
        st.error("Selected movie not found in the genres dataset.")
        return [], [], []
    
    recommended_movies_name = []
    recommended_movies_poster = []
    recommended_movies_id = []
    
    distances = sorted(list(enumerate(similarity2[index])), reverse=True, key=lambda x: x[1])
    
    for i in distances[1:6]:  # Get top 5 recommendations excluding the selected movie
        movie_id = movies.iloc[i[0]]["movie_id"]
        recommended_movies_poster.append(fetch_poster(movie_id))
        recommended_movies_name.append(movies.iloc[i[0]]["title"])
        recommended_movies_id.append(movies.iloc[i[0]]["movie_id"])
        
    return recommended_movies_name, recommended_movies_poster, recommended_movies_id

# Load movie data and similarity matrices
movies = pickle.load(open("Pickle/movie_list.pkl", "rb"))
similarity = pickle.load(open("Pickle/similarity.pkl", "rb"))
director = pickle.load(open("Pickle/director.pkl", "rb"))
cast_df = pickle.load(open("Pickle/Actor.pkl", "rb"))
Genres = pickle.load(open("Pickle/Genres.pkl", "rb"))
similarity2 = pickle.load(open("Pickle/similarity2.pkl", "rb"))

# Create a selectbox for movie selection
movie_list = movies["title"].values
selected_movie = st.selectbox(
    'Type or select a movie to get recommendation', movie_list)

# HTML to display if no movies are found
no_movies_found_html = """
<div style="text-align: center; font-size: 30px; color: red; font-weight: bold;">
    No Movies Found
</div>
"""

# Show recommendations when the button is clicked
if st.button("Show Recommendation"):
    
    st.subheader(':orange[Recommended Movies]')
    recommended_movies_name, recommended_movies_poster, recommended_movies_id = recommend(selected_movie)
    length = min(len(recommended_movies_name), 5)
    cols = st.columns(length)
    for i in range(length):
        with cols[i]:
            st.markdown(
                f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank"><img src="{recommended_movies_poster[i]}" width="250"></a>',
                unsafe_allow_html=True
            )
            st.markdown(
                f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank" style="text-decoration: none; color: inherit;">{recommended_movies_name[i]} </a>',
                unsafe_allow_html=True
            )
    
    
    st.subheader(f":orange[Other Movies with Same Genre]")
    recommended_movies_name, recommended_movies_poster, recommended_movies_id = recommend_genres(selected_movie)
    length = min(len(recommended_movies_name), 5)
    cols = st.columns(length)
    for i in range(length):
        with cols[i]:
            st.markdown(
                f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank"><img src="{recommended_movies_poster[i]}" width="250"></a>',
                unsafe_allow_html=True
            )
            st.markdown(
                f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank" style="text-decoration: none; color: inherit;">{recommended_movies_name[i]} </a>',
                unsafe_allow_html=True
            )
        
    
    st.subheader(f":orange[Movie's Director Other Movies]")
    recommended_movies_name, recommended_movies_poster, recommended_movies_id = recommend_Dir(selected_movie)
    length = min(len(recommended_movies_name), 5)
    
    if not recommended_movies_name:
        st.markdown(no_movies_found_html, unsafe_allow_html=True)
    else:
        cols = st.columns(length)
        for i in range(length):
            with cols[i]:
                st.markdown(
                    f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank"><img src="{recommended_movies_poster[i]}" width="250"></a>',
                    unsafe_allow_html=True
                )
                st.markdown(
                    f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank" style="text-decoration: none; color: inherit;">{recommended_movies_name[i]} </a>',
                    unsafe_allow_html=True
                )
            
    
    
    st.subheader(f":orange[Movie's Actor Other Movies]")
    recommended_movies_name, recommended_movies_poster, recommended_movies_id = recommend_with_cast(selected_movie)
    length = min(len(recommended_movies_name), 5)
    
    if not recommended_movies_name:
        st.markdown(no_movies_found_html, unsafe_allow_html=True)
    else:
        cols = st.columns(length)
        for i in range(length):
            with cols[i]:
                st.markdown(
                    f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank"><img src="{recommended_movies_poster[i]}" width="250"></a>',
                    unsafe_allow_html=True
                )
                st.markdown(
                    f'<a href="https://www.themoviedb.org/movie/{recommended_movies_id[i]}-{recommended_movies_name[i]}" target="_blank" style="text-decoration: none; color: inherit;">{recommended_movies_name[i]} </a>',
                    unsafe_allow_html=True
                )
    st.write("")
    st.write("")
    st.write("")
    st.write("")
    st.write("")
    st.write("")

# Load custom CSS styles
with open('style.css') as css:
    st.markdown(f'<style>{css.read()}</style>', unsafe_allow_html=True)
