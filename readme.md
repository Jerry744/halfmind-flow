# Halfmind Flow

**Halfmind Flow** is an experimental project exploring how radar sensing can be used to detect and support focus during work. By analyzing subtle human presence and movement patterns, Halfmind Flow aims to help individuals become more aware of their work states and build healthier, more sustainable focus habits.

## What is Halfmind Flow?

Halfmind Flow combines non-intrusive radar sensing with signal processing and simple feedback mechanisms. It monitors:

- **Presence**: Is someone at their desk?
- **Micro-movements**: Are they actively working, fidgeting, or absent?
- **Focus states**: How stable is their work posture over time?

This data can be used to trigger gentle nudges, reminders, or logs to help people reflect on their work rhythms.

## Features

- Real-time radar-based presence detection  
- Basic signal processing for classifying states (no presence, stable focus, fidgeting)  
- Audio and lighting interventions to nudge towards focus
- Visualization tools for data analysis  

## Tech Stack

- **Hardware:** 60 GHz FMCW Radar (Infineon BGT60TR13C)
- **Software:** Python for signal processing & classification (original work from: XXX)
- **Music** Generative music modified from XXX for running on Max/MSP
- **Visualization:** Streamlit or other simple dashboards
- **Optional:** Integration with Home Assistant or ambient devices (lights, sound cues)

## How it Works

The core loop:  
1. Raw radar signals are streamed and pre-processed.  
2. FFT is used to extract presence and movement features.  
3. A simple rule-based or machine learning classifier determines the user’s state.  
4. Feedback is provided (logs, ambient cues, or reminders).

## Roadmap

- [ ] Improve signal classification accuracy with more training data  
- [ ] Add real-time adaptive feedback  
- [ ] Integrate with calendar or to-do apps  
- [ ] Test in real work environments with volunteers

## Contributing

Contributions are welcome! If you’d like to help with signal processing, hardware integrations, or user experience design, please open an issue or submit a pull request.

## License

??? License — see [`LICENSE`](./LICENSE) for details.

## Acknowledgements

Halfmind Flow is my graduation project for defending the degree of Master of Science in Integrated Product Design at Technology University of Delft. It explored into ambient computing and human focus. Inspired by research on non-intrusive sensing, attention management, and mindful work environments.