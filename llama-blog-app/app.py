import boto3
import json
from botocore.exceptions import ClientError
from flask import Flask, render_template, request, Response

# --- Flask App Setup ---
app = Flask(__name__)

# --- AWS Bedrock Client ---
# Make sure your AWS credentials are configured (e.g., via `aws configure`)
try:
    bedrock_client = boto3.client("bedrock-runtime", region_name="us-west-2")
    model_id = "meta.llama3-70b-instruct-v1:0"
except Exception as e:
    print(f"Error creating Boto3 client: {e}")
    # In a real app, you might exit or handle this more gracefully
    bedrock_client = None

# --- Main Route (Serves the HTML Page) ---
@app.route('/')
def index():
    """Serves the main index.html page."""
    return render_template('index.html')

# --- Streaming Route (The "Magic") ---
@app.route('/generate-blog', methods=['POST'])
def generate_blog():
    """
    Handles the POST request from the frontend and streams the
    Llama 3 response back to the client.
    """
    if bedrock_client is None:
        return "Backend Bedrock client not initialized.", 500

    # Get the topic from the form data
    try:
        data = request.get_json()
        topic = data.get('topic', 'A default topic about AI')
    except Exception:
        topic = "A default topic about AI"

    # --- 1. Construct the Llama 3 Prompt ---
    # We use a system prompt for better instructions
    system_prompt = """
    You are an expert content marketer and SEO specialist. 
    Write a high-quality, engaging, and publish-ready blog post.
    Format the output in clean Markdown.
    Start directly with the blog post content.
    """
    
    user_prompt = f"Write a blog post on the topic: '{topic}'"
    
    formatted_prompt = f"""
    <|begin_of_text|><|start_header_id|>system<|end_header_id|>
    {system_prompt}
    <|eot_id|><|start_header_id|>user<|end_header_id|>
    {user_prompt}
    <|eot_id|><|start_header_id|>assistant<|end_header_id|>
    """

    # --- 2. Format the Bedrock Request ---
    # Note: We are now using invoke_model_with_response_stream
    body = json.dumps({
        "prompt": formatted_prompt,
        "max_gen_len": 2048,
        "temperature": 0.5,
    })

    # --- 3. Define the Streaming Generator ---
    def generate_text_stream():
        """This generator function streams the response."""
        try:
            # Invoke the model with streaming
            response = bedrock_client.invoke_model_with_response_stream(
                modelId=model_id,
                body=body
            )
            
            # Get the stream from the response
            stream = response.get('body')
            
            if stream:
                for event in stream:
                    # Get the chunk of data
                    chunk = event.get('chunk')
                    if chunk:
                        # Decode the chunk and parse the JSON
                        chunk_data = json.loads(chunk.get('bytes').decode())
                        
                        # Get the generated text
                        text_chunk = chunk_data.get('generation', '')
                        
                        # Yield the text chunk in SSE format
                        # The "data: " prefix is required for SSE
                        yield f"data: {json.dumps({'text': text_chunk})}\n\n"

        except ClientError as e:
            print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            print(f"ERROR: General exception: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Signal the end of the stream
        yield "data: [END_OF_STREAM]\n\n"

    # Return a new Response object, using the generator
    # The mimetype 'text/event-stream' is crucial for SSE
    return Response(generate_text_stream(), mimetype='text/event-stream')

# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)