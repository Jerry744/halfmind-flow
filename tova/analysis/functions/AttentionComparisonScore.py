import sys
sys.path.append('.')
from functions.dataset_visual_norm import tova_selected_data

def z_score(x, mean, std):
    return (x - mean) / std

def standard_score(z):
    return 100+15*z

def calculate_attention_score(meanHitRT_LF, dprime_HF, SDHitRT, age, sex, debug=True):
    # sex: 'male' or 'female'
    # age: automatically convert to the lower 10s (e.g. 23 -> 20, representing 20-29)
    age = int(age/10)*10
    group = tova_selected_data[age][sex]
    meanHitRT_LF_z = z_score(meanHitRT_LF, group['response_time_H2']['mean'], group['response_time_H2']['sd'])
    dprime_HF_z = z_score(dprime_HF, group['d_prime_H2']['mean'], group['d_prime_H2']['sd'])
    SDHitRT_z = z_score(SDHitRT, group['variability_total']['mean'], group['variability_total']['sd'])
    if debug:
        print(f"meanHitRT_LF {meanHitRT_LF:.2f}, standard score: {standard_score(meanHitRT_LF_z):.2f}")
        print(f"dprime_HF {dprime_HF:.2f}, standard score: {standard_score(dprime_HF_z):.2f}")
        print(f"SDHitRT {SDHitRT:.2f}, standard score: {standard_score(SDHitRT_z):.2f}")
    return -meanHitRT_LF_z + dprime_HF_z - SDHitRT_z + 1.8

def load_iqdat_file(file_path):
    # Read the file as text and replace single quotes with periods
    import pandas as pd
    import io
    import os
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    if file_path.lower().endswith('.iqdat'):
        content = content.replace(",", ".")
        df = pd.read_csv(io.StringIO(content), sep='\t')
    elif file_path.lower().endswith('.csv'):
        df = pd.read_csv(io.StringIO(content), sep=',')
    # Try to get age and sex, if not found, ask for input
    try:
        age = int(df['age'].iloc[0])
    except Exception:
        age = int(input('Please input the subject\'s age: '))
    try:
        sex = df['gender'].iloc[0]
    except Exception:
        sex = input('Please input the subject\'s gender (Male/Female, case sensitive): ')
    meanHitRT_LF = float(df['meanHitRT_LF'].iloc[0])
    dprime_HF = float(df['dprime_HF'].iloc[0])
    SDHitRT = float(df['SDHitRT'].iloc[0])
    # Parse user name from file name (after second underscore)
    base = os.path.basename(file_path)
    parts = base.split('_', 2)
    user_name = ''
    if len(parts) >= 3:
        user_name = parts[2].split('.', 1)[0]
        if user_name:
            print(f"user name: {user_name}")
    print([meanHitRT_LF, dprime_HF, SDHitRT, age, sex])
    return [meanHitRT_LF, dprime_HF, SDHitRT, age, sex]
