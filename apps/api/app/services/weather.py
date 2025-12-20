import random

def determine_weather() -> str:
    # 晴(0.55) / 曇(0.30) / 雨(0.15)
    r = random.random()
    if r < 0.55:
        return "sunny"
    elif r < 0.85:
        return "cloudy"
    else:
        return "rain"

def get_weather_effect(weather: str) -> float:
    # g_W: 晴(0) / 曇(-0.2) / 雨(-0.6)
    if weather == "sunny":
        return 0.0
    elif weather == "cloudy":
        return -0.2
    elif weather == "rain":
        return -0.6
    return 0.0
