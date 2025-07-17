import functions.AttentionComparisonScore as acs
import os
from pathlib import Path

def process_folder(folder_path, min_size_kb=1.5, max_size_kb=3.0, debug=True):
    results = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.iqdat') or file.endswith('.csv'):
                file_path = Path(root) / file
                file_size_kb = file_path.stat().st_size / 1024  # Convert to KB
                if min_size_kb <= file_size_kb <= max_size_kb:
                    try:
                        acs_sub = acs.load_iqdat_file(str(file_path))
                        participant = acs.calculate_attention_score(
                            acs_sub[0], acs_sub[1], acs_sub[2], age=acs_sub[3], sex=acs_sub[4], debug=debug)
                        results.append({
                            'file': str(file),
                            'data': participant
                        })
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
    
    return results

if __name__ == "__main__":
    debug = True
    is_male = False
    # # Calculate a single file by its file path
    # file_path = "/Users/zhengyang/Documents/ADHD/Experiment-1/Result/01-silence-ADHDmusic/13/1.iqdat"
    # acs_sub = acs.load_iqdat_file(file_path)
    # participant = acs.calculate_attention_score(acs_sub[0], acs_sub[1], acs_sub[2], is_male=is_male, debug=debug)
    # print("Test result 1")
    # print(participant)


    # automate a folder calculation
    folder_path = "/Users/zhengyang/Documents/ADHD/Experiment-1/Result/other/mio/"
    results = process_folder(folder_path, debug=debug)
    for result in results:
        print(f"\nFile: {result['file']}")
        print(result['data'])


