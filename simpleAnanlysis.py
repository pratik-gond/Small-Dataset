import pandas as pd
import json
import requests
from PIL import Image as PILImage
from io import BytesIO
from openai import OpenAI
import os
import datetime

# Load your data
def load_data(file_path):
    df = pd.read_excel(file_path)
    return df

# Function to extract and identify unique restaurants
def identify_unique_restaurants(df):
    unique_restaurants = df['checklist_type'].unique()
    restaurant_counts = df['checklist_type'].value_counts().to_dict()
    
    print(f"Found {len(unique_restaurants)} unique restaurants:")
    for i, restaurant in enumerate(unique_restaurants):
        count = restaurant_counts[restaurant]
        print(f"{i+1}. {restaurant} ({count} entries)")
    print("Idetifu_unique_restaurants function completed")
    return unique_restaurants

# Function to filter data for specific restaurants
def filter_by_restaurants(df, selected_restaurants):
    return df[df['checklist_type'].isin(selected_restaurants)]

# Functions to handle images
def get_image_url(row):
    try:
        # Try both possible column names
        column_name = 'upload_links (images)' if 'upload_links (images)' in row else 'upload_links'
        
        if column_name not in row:
            print(f"Key '{column_name}' not found in the row.")
            return None
        
        if pd.isna(row[column_name]):
            return None
            
        links_string = row[column_name].strip().strip('"')
        print(f"Processing links string: {links_string}")

        urls = json.loads(links_string)
        print(f"Parsed URLs: {urls}")
        
        if isinstance(urls, list) and urls:
            return urls[0]
        else:
            print("No valid URL found in the list.")
            return None
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"Error parsing upload_links: {e}")
        return None

# Image analysis using OpenAI with retry logic
def analyze_image(client, row, max_retries=3):
    question = row['question']
    image_url = get_image_url(row)
    
    if not image_url:
        return {
            "criteria_met": "Unknown", 
            "explanation": "No valid image URL", 
            "improvements": "",
            "image_quality_issues": ["no_image"],
            "severity": "Unknown",
            "tags": ["no_image", "missing_data", "technical_error"]
        }
    
    prompt = f"""
    You are a food safety manager analyzing a cafeteria image.
    Question to evaluate: {question}
    
    IMPORTANT INSTRUCTIONS FOR IMAGE QUALITY AND COMPLIANCE:
    1. First, assess if the image is too dark or too blurry. Include this in your analysis.
    2. CRITICAL: If the question specifically asks for or expects a blank photo, empty area, or clean surface, 
       AND the image shows an appropriate empty/blank/dark area, this should be marked as "Yes" (compliant).
    3. A dark or blurry image should ONLY be marked as compliant if:
       - The question explicitly asks for documentation of an empty, vacant, or clear area, OR
       - The question is checking if something is properly put away/not present, AND
       - The darkness or blurriness doesn't prevent you from determining compliance
    
    Analyze the image and provide a detailed evaluation in JSON format with the following fields:
    1. "criteria_met": "Yes" if compliant with food safety standards, "No" if not compliant, "Unable to determine" if image quality prevents assessment
    2. "explanation": Detailed explanation of your assessment (2-3 sentences)
    3. "improvements": Specific actionable recommendations if issues are found (leave empty if no issues)
    4. "severity": Categorize as "Critical", "Major", "Minor", or "None" based on the safety impact
    5. "image_quality_issues": A list of quality issues detected in the image (e.g., ["too_dark", "too_blurry"], or ["none"] if no issues)
    6. "quality_assessment": Brief comment on whether image quality affected your assessment
    7. "tags": A list of 3-5 tags that best describe the analysis. Include tags related to:
       - Area of concern (kitchen, storage, dining, etc.)
       - Type of issue (cleanliness, organization, maintenance, etc.)
       - Specific observation (expired_food, improper_storage, cross_contamination, etc.)
       - Any other relevant categorization
       
       Examples of good tags:
       - For a clean kitchen: ["kitchen", "compliant", "good_hygiene", "well_maintained", "organized"]
       - For a food storage issue: ["storage", "temperature_abuse", "food_safety", "needs_improvement", "perishable_items"]
       - For an empty area check: ["vacant_space", "compliant", "no_obstacles", "clear_pathway"]
    
    Remember: If the question specifically says to click a blank image if not applicable or a clear image, this should be marked compliant.A dark image for a question that doesnt mention the image to be dark or blank implies non-compliance.Make the compliance_status as a No in that case.And for other non complient images.

    """

    # Implement retry logic
    retries = 0
    while retries < max_retries:
        try:
            # Verify the image is accessible before passing to OpenAI
            try:
                # Test image URL with a head request
                response = requests.head(image_url, timeout=10)
                response.raise_for_status()
            except requests.exceptions.RequestException:
                # If head request fails, try to download the image directly
                print(f"Testing image accessibility for {image_url}...")
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                # If we got here, the image is accessible
                print("Image is accessible.")

            # Now proceed with OpenAI analysis
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                            },
                        },
                    ],
                }],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
        
        except Exception as e:
            retries += 1
            print(f"Attempt {retries}/{max_retries} failed: {str(e)}")
            if retries < max_retries:
                print(f"Retrying in {2**retries} seconds...")
                import time
                time.sleep(2**retries)  # Exponential backoff
            else:
                print(f"All {max_retries} attempts failed. Last error: {e}")
                return {
                    "criteria_met": "Error", 
                    "explanation": f"Analysis failed after {max_retries} attempts: {str(e)}",
                    "improvements": "",
                    "image_quality_issues": ["analysis_error"],
                    "severity": "Unknown",
                    "quality_assessment": "Error in analysis process",
                    "tags": ["error", "analysis_failed", "technical_issue"]
                }

# Main analysis function
def analyze_selected_restaurants(df, selected_restaurants, api_key):
    # Configure OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Filter data for selected restaurants
    filtered_df = filter_by_restaurants(df, selected_restaurants).copy()
    
    # Show count of entries for each selected restaurant
    restaurant_counts = filtered_df['checklist_type'].value_counts()
    print("\nEntries to be analyzed:")
    for restaurant, count in restaurant_counts.items():
        print(f"{restaurant}: {count} entries")
    
    # Create an output file path
    output_file = f"analysis_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Add new columns to the dataframe for analysis results
    filtered_df['compliance_status'] = None
    filtered_df['explanation'] = None
    filtered_df['improvement_suggestions'] = None
    filtered_df['severity_level'] = None
    filtered_df['image_quality_issues'] = None
    filtered_df['quality_assessment'] = None
    filtered_df['tags'] = None
    filtered_df['analysis_date'] = None
    
    # Analyze each row
    total_rows = len(filtered_df)
    for idx, row in filtered_df.iterrows():
        print(f"\nAnalyzing image {filtered_df.index.get_loc(idx) + 1}/{total_rows} for {row['checklist_type']}")
        print(f"Question: {row['question']}")
        
        result = analyze_image(client, row)
        
        # Format image quality issues as string if it's a list
        image_quality_issues = result.get('image_quality_issues', ['none'])
        if isinstance(image_quality_issues, list):
            image_quality_issues = ', '.join(image_quality_issues)
        
        # Format tags as string if it's a list
        tags = result.get('tags', ['untagged'])
        if isinstance(tags, list):
            tags = ', '.join(tags)
        
        # Update the dataframe with analysis results
        filtered_df.at[idx, 'compliance_status'] = result.get('criteria_met', 'Unknown')
        filtered_df.at[idx, 'explanation'] = result.get('explanation', '')
        filtered_df.at[idx, 'improvement_suggestions'] = result.get('improvements', '')
        filtered_df.at[idx, 'severity_level'] = result.get('severity', 'Unknown')
        filtered_df.at[idx, 'image_quality_issues'] = image_quality_issues
        filtered_df.at[idx, 'quality_assessment'] = result.get('quality_assessment', '')
        filtered_df.at[idx, 'tags'] = tags
        filtered_df.at[idx, 'analysis_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        
        print(f"Compliance: {filtered_df.at[idx, 'compliance_status']}")
        print(f"Severity: {filtered_df.at[idx, 'severity_level']}")
        print(f"Tags: {filtered_df.at[idx, 'tags']}")
        
        # Save progress after each analysis
        filtered_df.to_excel(output_file, index=False)
        print(f"Progress saved to {output_file}")

    print(f"\nAnalysis complete! Results saved to {output_file}")
    return filtered_df

# Main function
def main():
    # Get file path
    file_path = input("Enter path to your Excel file: ")
    
    # Load the data
    try:
        df = load_data(file_path)
        print(f"Loaded data with {len(df)} rows and {df.shape[1]} columns")
    except Exception as e:
        print(f"Error loading data: {e}")
        return
    
    # Identify unique restaurants
    unique_restaurants = identify_unique_restaurants(df)
    print("unique_restaurants to main")
    
    # Let user select restaurants
    print("\nSelect restaurants to analyze (enter numbers separated by commas):")
    selection = input("> ")
    try:
        selected_indices = [int(idx.strip()) - 1 for idx in selection.split(',')]
        selected_restaurants = [unique_restaurants[idx] for idx in selected_indices if 0 <= idx < len(unique_restaurants)]
        
        print(f"\nSelected restaurants for analysis: {selected_restaurants}")
    except Exception as e:
        print(f"Error selecting restaurants: {e}")
        return
    
    # Get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    
    # Run analysis
    analyzed_df = analyze_selected_restaurants(df, selected_restaurants, api_key)
    
    # Print summary
    print("\n=== ANALYSIS SUMMARY ===")
    compliance_counts = analyzed_df['compliance_status'].value_counts()
    severity_counts = analyzed_df['severity_level'].value_counts()
    quality_issues_counts = analyzed_df['image_quality_issues'].str.contains('too_dark|too_blurry').sum()
    
    # Get most common tags
    all_tags = []
    for tag_str in analyzed_df['tags'].dropna():
        all_tags.extend([tag.strip() for tag in tag_str.split(',')])
    
    from collections import Counter
    top_tags = Counter(all_tags).most_common(10)
    
    # Restaurant-specific summary
    print("\nResults by restaurant:")
    for restaurant in analyzed_df['checklist_type'].unique():
        rest_df = analyzed_df[analyzed_df['checklist_type'] == restaurant]
        rest_compliance = rest_df['compliance_status'].value_counts()
        rest_severity = rest_df['severity_level'].value_counts()
        
        print(f"\n{restaurant} ({len(rest_df)} entries):")
        print("  Compliance:")
        for status, count in rest_compliance.items():
            print(f"    {status}: {count}")
        print("  Severity:")
        for level, count in rest_severity.items():
            print(f"    {level}: {count}")
    
    print("\nOverall Compliance Status:")
    print(compliance_counts)
    
    print("\nOverall Severity Levels:")
    print(severity_counts)
    
    print("\nTop 10 Tags:")
    for tag, count in top_tags:
        print(f"  {tag}: {count}")
    
    print(f"\nImages with quality issues: {quality_issues_counts} of {len(analyzed_df)}")

if __name__ == "__main__":
    main()