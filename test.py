import google.generativeai as genai
genai.configure(api_key='AIzaSyDc6MvRimnmEco6FWL4EfAYq9TQ6yj9XqU')
for model in genai.list_models():
    print(model.name)