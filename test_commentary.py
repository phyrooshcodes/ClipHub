import json
import sys
import logging
from modules.commentary_generator import generate_commentary

logging.basicConfig(level=logging.INFO)

def test_mode(mode_name, title, transcript, context):
    print(f"\n--- Testing Mode: {mode_name} ---")
    
    # Normally, commentary_generator is called with mode implied by UI or settings.
    # Wait, our current generate_commentary doesn't take 'mode' explicitly, 
    # it generates a full structure, and the pipeline strips parts based on the mode!
    # Let's verify the full generation works.
    
    try:
        result = generate_commentary(
            clip_transcript=transcript,
            surrounding_context=context,
            topic=title
        )
        print("Success! Generated Data:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"Failed: {e}")
        return False

if __name__ == "__main__":
    title = "The Secret to Happiness"
    transcript = "Happiness isn't about getting what you want all the time. It's about loving what you have."
    context = "Before this, we talked about wealth. And I said to him, Happiness isn't about getting what you want all the time. It's about loving what you have. That is the fundamental truth."
    
    test_mode("Full Generation", title, transcript, context)
