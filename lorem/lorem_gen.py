import random
try:
    from .lorem_dict import word as word_dict   # khi import dưới dạng package (run.py)
except ImportError:
    from lorem_dict import word as word_dict    # khi chạy trực tiếp file này

def gen_lorem(num_words: int = None) -> str:
    """
    Generates optimized lorem ipsum text using words from lorem_dict.
    Properly formats punctuation and sentence capitalization.
    """
    # Extract clean words (excluding punctuation from dictionary)
    all_items = list(word_dict.values())
    words = [w for w in all_items if w not in ('.', ',')]
    
    if not num_words:
        num_words = random.randint(20, 30)
        
    # Standard prefix words
    prefix = ["lorem", "ipsum", "onfen", "roble", "hon"]
    
    # Generate the list of words
    generated_words = []
    
    # Prepend the prefix words first
    for w in prefix:
        if len(generated_words) < num_words:
            generated_words.append(w)
            
    # Fill the remaining slots with random words
    while len(generated_words) < num_words:
        word = random.choice(words)
        # Avoid duplicate consecutive words
        if generated_words and word == generated_words[-1]:
            continue
        generated_words.append(word)
        
    # Group words into sentences
    sentences = []
    idx = 0
    total = len(generated_words)
    
    while idx < total:
        sent_len = random.randint(8, 15)
        # Prevent leaving a very short trailing sentence
        if idx + sent_len + 3 > total:
            sent_len = total - idx
            
        sent_words = generated_words[idx : idx + sent_len]
        idx += sent_len
        
        if not sent_words:
            break
            
        # Capitalize the first word of the sentence
        sent_words[0] = sent_words[0].capitalize()
        
        # Format punctuation
        # Always place comma after "hon" if this is the first sentence
        if idx - len(sent_words) == 0 and len(sent_words) >= 5 and sent_words[4].lower().startswith("hon"):
            sent_words[4] += ","
        elif len(sent_words) >= 8:
            comma_idx = random.randint(3, len(sent_words) - 4)
            sent_words[comma_idx] += ","
            
        # End sentence with a period
        sent_words[-1] += "."
        
        sentences.append(" ".join(sent_words))
        
    text = " ".join(sentences)
    return text

if __name__ == "__main__":
    print(gen_lorem())