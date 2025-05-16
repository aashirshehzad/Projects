<h1 align="center">
  Movie Recommendation System Using ML with UI
</h1>

## Overview

The Movie Recommendation System is a machine learning-powered application featuring an intuitive user interface built with Streamlit. This system leverages data preprocessing, TF-IDF vectorization, and cosine similarity to recommend movies based on user preferences.This project is based on <strong>Content-Based </strong> Filtering.

---

## Table of Contents

- Features
- Technologies Used
- Installation
- Project Structure
- How It Works
- UI Pictures
- Contribution
- License
- Contact

---

## Features

- **User-Friendly Interface:** Built with Streamlit for an easy and interactive user experience.
- **Movie Recommendations:** Provides movie recommendations based on similarity scores.
- **Poster Fetching:** Fetches movie posters using the TMDB API for a visually appealing display.

---

## Technologies Used

- **Frontend:** Streamlit
- **Backend:** Python
- **Libraries:** Pandas, Numpy, Scikit-learn, NLTK
- **API:** TMDB API

---

## Installation

### Prerequisites

- Python 3.7 or higher
- Pip (Python package installer)

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI.git
   cd Movie-Recommendation-System-Using-ML-with-Ui
2. **Create and activate a virtual environment (optional but recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
3. **Install the required packages:**
   ```bash
   pip install -r requirements.txt
4. **Download NLTK data:**
   ```bash
   python -m nltk.downloader stopwords

---

## Project Structure
1. **Code:** Include Project_Code.ipynb(Jupyter notebook) and Project_app.py(UI)
2. **Drafts:** Project Documentations
3. **Presentation**
4. **Project Proposal:** Project proposal video
5. **requirements.txt:** include python libraries
6. **README.md:** Project readme file

---

## Usage
1. **Run the Streamlit app:**
   ```bash
   streamlit run Project_app.py
2. **Open your web browser and go to:**
   ```bash
   http://localhost:8501
3. Select a movie from the dropdown menu to get recommendations.

---

## How It Works
1. **Data Preprocessing:**
   - Consolidates various movie attributes (genres, keywords, cast, etc.) into a single 'tags' column.
   - Applies text processing techniques like lowercasing and stemming.
3. **Vectorization and Similarity Calculation:**
   - Uses TF-IDF vectorization to convert text data into numerical vectors.
   - Computes cosine similarity between these vectors to measure the similarity between different movies.
5. **Recommendation:**
   - Provides movie recommendations based on the cosine similarity scores.
 
 ---
 
## UI Pictures
<div align="center">
  <img src="https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI/assets/112303807/d76f4312-d9a0-4159-b422-321a81f54ba2" alt="UI Image 1" width="800">
  <img src="https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI/assets/112303807/2de36d60-a7c3-44c0-b350-1a484d68e972" alt="UI Image 2" width="800">
  <img src="https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI/assets/112303807/469802b4-aadc-4088-b2c0-1a505fc65a9b" alt="UI Image 3" width="800">
  <img src="https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI/assets/112303807/8531e5fd-0a06-47e2-858f-c399b8825565" alt="UI Image 3" width="800">
  <img src="https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI/assets/112303807/37479345-9b88-497e-aa76-0c0ccf23b722" alt="UI Image 3" width="800">
</div>
 
---
 
## Contribution
Feel free to fork this project, submit issues, and send pull requests. Contributions are welcome!
 
---
 
## License
This project is licensed under the MIT License.
 
---
 
## Contact
For any queries, reach out to [Kashif Khan](https://github.com/kashifsahilks906).

---

For more details, visit the [repository](https://github.com/kashifsahilks906/ML-Powered-Movie-Recommendation-UI).
