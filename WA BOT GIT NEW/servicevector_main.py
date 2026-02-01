from sentence_transformers import SentenceTransformer
from supabase import create_client

# Supabase Credentials (replace with your actual credentials)
#SUPABASE_URL = "https://qwvglybkftfptzlhdffg.supabase.co"
#SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3dmdseWJrZnRmcHR6bGhkZmZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU0MTA4NDQsImV4cCI6MjA3MDk4Njg0NH0.A89YzGK1i5YxNjRHAJkwxLQOAC8WJ4xgb35UKyFY7ro"
SUPABASE_URL="https://umpbmweobqlowgavdydu.supabase.co"
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVtcGJtd2VvYnFsb3dnYXZkeWR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwMDM3MTIsImV4cCI6MjA4MDU3OTcxMn0.jUVCioepUoTbadeqykzPq_73WsCScAP8XrtqvOJFhR0"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load the sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

def vectorize_services():
    """Vectorize all active clinic services and upsert into service_vectors table"""
    try:
        # Fetch all active services
        response = supabase.table('c_a_clinic_service') \
            .select('id, service_name, description, side_info, category') \
            .eq('is_active', True) \
            .execute()
        
        if not response.data:
            print("No active services found.")
            return
        
        services = response.data
        print(f"Processing {len(services)} services...")
        
        for service in services:
            # Combine text fields
            text_parts = [
                service.get('service_name', ''),
                service.get('description', ''),
                service.get('side_info', ''),
                service.get('category', '')
            ]
            combined_text = ' '.join(filter(None, text_parts)).strip()
            
            if not combined_text:
                print(f"Skipping service {service['id']} - no text to vectorize")
                continue
            
            # Generate vector
            vector = model.encode(combined_text).tolist()
            
            # Upsert into service_vectors
            supabase.table('c_service_vectors').upsert(
                {'service_id': service['id'], 'vector': vector},
                on_conflict='service_id'
            ).execute()
            
            print(f"Vectorized and upserted service {service['id']}")
        
        print("Vectorization complete!")
        
    except Exception as e:
        print(f"Error during vectorization: {e}")

if __name__ == '__main__':
    vectorize_services()