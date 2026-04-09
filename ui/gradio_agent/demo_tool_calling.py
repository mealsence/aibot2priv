#!/usr/bin/env python3
"""
Direct Tool Calling Demo

This implementation uses standard Tool/ToolCall approach instead of PlanAndRobotControl.
It demonstrates direct LLM tool calling with immediate execution.
"""

import argparse
import gradio as gr
import tempfile
from gtts import gTTS
import rclpy
import base64
import json
import io
from pathlib import Path

import openai
from openai import OpenAI
import os
from google import genai
from typing import Optional, List, Dict, Tuple
import numpy as np

from dotenv import load_dotenv
load_dotenv()

# ===== Additional imports for streaming voice chat functionality =====
from dataclasses import dataclass
from pydub import AudioSegment

from mbodied.types.sense.vision import Image as MbodiedImage
from mbodied.agents.language import LanguageAgent
from mbodied.agents.language.utils import function_to_tool
from mbodied.types.tool import Tool, ToolCall
from image_getter import ImageProvider, capture_image
from robot_tools import get_robot_tools, get_tool_by_name, preload_all_controllers
from utils import determine_pause  # pause detection
from speaking import speaking  # streaming TTS stub
from simple_camera_stream import CameraStreamer  # Live camera streaming

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# monkey patch to make function_to_tools output work with lists
def patch_tool_schema(tool):
    # Patch OpenAI schema for array parameters missing 'items'
    parameters = tool.function.parameters
    for param, schema in parameters.get("properties", {}).items():
        if schema.get("type") == "array" and "items" not in schema:
            # Default to number, or customize as needed
            schema["items"] = {"type": "number"}
    return tool




# Parse command line arguments
parser = argparse.ArgumentParser(description='Robot control interface with direct tool calling')
parser.add_argument('--llm', type=str, default='openai', choices=['openai', 'gemini'],
                    help='Language model to use: "openai" or "gemini" (default: openai)')
parser.add_argument('--transcriber', default='meralion', choices=['openai', 'gemini', 'meralion'],
                    help='Transcriber model to use (default: meralion)')
parser.add_argument('--preload-policy', action='store_true',
                    help='Pre-load VLA policy at startup instead of on first use (default: False)')
parser.add_argument('--discover-arm-server', action='store_true',
                    help='Run action server discovery at startup instead of using position topic directly (default: False, uses faster position topic)')
args = parser.parse_args()

# System prompt file for tool calling
tool_calling_system_prompt = "system_prompt_tool_calling.txt"


# (Removed VoiceChatState and streaming helpers)


class LLMError(RuntimeError):
    """Raised when the language-agent call fails."""
    pass

def get_meralion_client(api_key="EMPTY", base_url="http://meralion.org:8703/v1"):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    models = client.models.list()
    model_name = models.data[0].id
    return client, model_name

def get_meralion_response(client, text_input, base64_audio_input=None):
    meralion_client, model_name = get_meralion_client(base_url="http://meralion.org:8703/v1")
    generation_parameters = dict(
        model=model_name,
        max_completion_tokens=1024,
        temperature=0.0,
        top_p=0.9,
        extra_body={
            "repetition_penalty": 1.05,
            "top_k": 50,
            "length_penalty": 1.0,
            "logits_processors": [
                {"qualname": "vllm_plugin_meralion.NoRepeatNGramLogitsProcessor", "args": [3]}
            ]
        },
        seed=42,
        stream=False
    )
    prompt_template = "Instruction: {text_input} \nFollow the text instruction based on the following audio: <SpeechHere>"
    if base64_audio_input:
        content = [
            {
                "type": "text",
                "text": prompt_template.format(text_input=text_input)
            },
            {
                "type": "audio_url",
                "audio_url": {
                    "url": f"data:audio/ogg;base64,{base64_audio_input}"
                },
            },
        ]
    else:
        content = text_input

    response_obj = meralion_client.chat.completions.create(
        messages=[{
            "role": "user",
            "content": content,
        }],
        **generation_parameters
    )
    print(f"Transcribed: {response_obj.choices[0].message.content}")
    return response_obj.choices[0].message.content


# ===== Voice chat state and helpers =====
@dataclass
class VoiceChatState:
    """Container for voice chat state managed across callbacks."""

    stream: Optional[np.ndarray] = None
    sampling_rate: int = 0
    pause_detected: bool = False
    stopped: bool = False
    started_talking: bool = False
    conversation: list | None = None

    def __post_init__(self) -> None:
        if self.conversation is None:
            self.conversation = []


def voicechat_process_audio(audio: Tuple[int, np.ndarray], state: VoiceChatState):
    """Accumulate audio chunks and detect user pause.

    Returns (input_audio_update_or_None, updated_state).
    """
    sampling_rate, chunk = audio

    if state.stream is None:
        state.stream = chunk
        state.sampling_rate = sampling_rate
    else:
        state.stream = np.concatenate((state.stream, chunk))

    pause_detected, started_talking = determine_pause(state.stream, state.sampling_rate, state)
    state.pause_detected = pause_detected
    state.started_talking = started_talking

    if state.pause_detected and state.started_talking:
        return gr.Audio(recording=False), state

    return None, state


def voicechat_start_recording_user(state: VoiceChatState):
    if not state.stopped:
        return gr.Audio(recording=True)
    return gr.Audio(recording=False)


class RobotInterface:
    def __init__(self):
        # Create language agent
        self.agent = self._create_language_agent()
        self._reset_state()

        self.latest_image: Optional[MbodiedImage] = None

        # Initialize camera system
        self.camera_intrinsics = {"fx": 634.09, "fy": 566.49, "cx": 640, "cy": 360}
        self.image_provider = ImageProvider()

        # Initialize live camera streaming
        self.camera_streamer = None
        self._init_camera_streaming()


        # Initialize tool calling system
        self.tools = self._create_tools()
        self.tool_execution_history = []
        self._tool_name_to_func = {func.__name__: func for func in get_robot_tools()}

        if args.llm == "openai":
            self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        elif args.llm == "gemini":
            self.client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    def _init_camera_streaming(self):
        """Initialize live camera streaming for the interface."""
        try:
            self.camera_streamer = CameraStreamer(source="auto")
            self.camera_streamer.start_streaming()
            print("✅ Live camera streaming initialized")
        except Exception as e:
            print(f"⚠️ Camera streaming initialization failed: {e}")
            self.camera_streamer = None

    def get_live_camera_frame(self):
        """Get the latest frame from live camera stream, properly sized for display."""
        if self.camera_streamer and self.camera_streamer.running:
            frame = self.camera_streamer.get_latest_frame()
            if frame:
                # Convert to PIL Image if needed and resize to fill the display better
                from PIL import Image as PILImage
                if isinstance(frame, PILImage.Image):
                    # Create a consistent size image that will fill the gradio component
                    target_width, target_height = 800, 600
                    
                    # Calculate scaling to fill the target size while maintaining aspect ratio
                    original_width, original_height = frame.size
                    scale_w = target_width / original_width
                    scale_h = target_height / original_height
                    
                    # Use the larger scale to ensure the image fills the space
                    scale = max(scale_w, scale_h)
                    
                    # Calculate new dimensions
                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)
                    
                    # Resize the image
                    resized_frame = frame.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
                    
                    # Crop to exact target size if needed (center crop)
                    if new_width > target_width or new_height > target_height:
                        left = (new_width - target_width) // 2
                        top = (new_height - target_height) // 2
                        right = left + target_width
                        bottom = top + target_height
                        resized_frame = resized_frame.crop((left, top, right, bottom))
                    
                    return resized_frame
                
                return frame
        
        # Fallback to captured image if live stream unavailable
        if self.latest_image:
            frame = self.latest_image.pil
            if frame:
                # Apply the same resizing logic to fallback image
                from PIL import Image as PILImage
                target_width, target_height = 800, 600
                original_width, original_height = frame.size
                scale_w = target_width / original_width
                scale_h = target_height / original_height
                scale = max(scale_w, scale_h)
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
                resized_frame = frame.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
                
                if new_width > target_width or new_height > target_height:
                    left = (new_width - target_width) // 2
                    top = (new_height - target_height) // 2
                    right = left + target_width
                    bottom = top + target_height
                    resized_frame = resized_frame.crop((left, top, right, bottom))
                
                return resized_frame
        
        return None

    def get_camera_status(self):
        """Get camera streaming status."""
        if self.camera_streamer:
            status = self.camera_streamer.get_status()
            return f"🟢 Live: {status['backend']}" if status['running'] else "🔴 Stopped"
        return "❌ Not available"

    def _create_language_agent(self):
        """Create the language agent for tool calling."""
        # Load system prompt from external file
        try:
            with open(tool_calling_system_prompt, "r") as file:
                context = file.read()
                print(f"✅ Loaded system prompt from: {tool_calling_system_prompt}")
        except FileNotFoundError:
            print(f"⚠️ Warning: {tool_calling_system_prompt} not found, using fallback prompt")
            # Fallback inline prompt
            context = """You are a robot assistant that can both have conversations and control a robot when needed.
                        Use available robot tools for physical tasks. Respond naturally for conversation."""

        api_key = None
        if args.llm == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("Please set the OPENAI_API_KEY environment variable")
        elif args.llm == "gemini":
            api_key = os.environ.get("GOOGLE_API_KEY") 
            if not api_key:
                raise ValueError("Please set the GOOGLE_API_KEY environment variable")

        agent = LanguageAgent(
            context=context,
            api_key=api_key,
            model_src=args.llm
        )
        
        return agent

    def _reset_state(self):
        """Reset the internal state."""
        self.latest_query = None
        self.latest_response = None
        self.interrupt_flag = False
        self.is_executing = False
        self.latest_image = None
        self.tool_execution_history = []

    def _create_tools(self):
        """Create tools from robot functions using function_to_tool."""
        robot_functions = get_robot_tools()
        tools = []
        
        for func in robot_functions:
            tool = function_to_tool(func)
            tool = patch_tool_schema(tool) # patch for openai 
            tools.append(tool)
        
        print(f"🔧 Created {len(tools)} robot tools using function_to_tool:")
        for tool in tools:
            print(f"  - {tool.function.name}: {tool.function.description}")
        
        return tools

    def set_latest_image(self, image):
        """Set the latest image, casting to MbodiedImage if needed."""
        if not isinstance(image, MbodiedImage):
            image = MbodiedImage(image)
        self.latest_image = image

    def capture_current_image(self):
        """Capture current image from camera for vision questions."""
        try:
            image, _, _ = capture_image(self.image_provider, require_view_matrix=False)
            if image:
                self.set_latest_image(image)
                return True
        except Exception as e:
            print(f"Failed to capture image: {e}")
        return False

    def text_to_speech(self, text):
        """Convert text to speech using gTTS."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save(temp_file.name)
            return temp_file.name

    def transcribe_audio(self, audio_file):
        """Transcribe audio using selected transcriber."""
        try:
            if args.transcriber == "openai":
                with open(audio_file, "rb") as file:
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=file
                    )
                    return transcription.text
            elif args.transcriber == "gemini":
                prompt = "Transcribe the audio file."
                myfile = self.client.files.upload(file=audio_file)
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash", contents=[prompt, myfile]
                )
                return response.text
            elif args.transcriber == "meralion":
                audio_bytes = open(audio_file, "rb").read()
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                transcription = get_meralion_response(
                    client=self.client,
                    text_input="Transcribe the audio file.",
                    base64_audio_input=audio_base64
                )
                return transcription
            else:
                return "Transcription not supported for this model."
        
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""

    def interrupt_plan(self):
        """Interrupt current execution."""
        if self.is_executing:
            self.interrupt_flag = True
            return "Interrupt request sent. Robot will stop after current operation."
        elif not self.is_executing and not self.interrupt_flag:
            return "No execution is currently in progress."
        
        if self.interrupt_flag:
            return ""

    def _execute_tool_call(self, tool_call: ToolCall):
        """Execute a single tool call and return the result."""
        try:
            function_name = tool_call.function.name
            arguments = tool_call.function.arguments
            
            print(f"🛠️ Executing tool: {function_name}")
            print(f"   Arguments: {arguments}")
            
            # Parse arguments if they're a string
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            
            # Get the tool function
            tool_function = get_tool_by_name(function_name)
            if not tool_function:
                return {"success": False, "error": f"Unknown tool: {function_name}"}
            
            # Execute the tool function
            result = tool_function(**arguments)
            
            # Store in execution history
            self.tool_execution_history.append({
                "tool": function_name,
                "arguments": arguments,
                "result": result
            })
            
            print(f"   Result: {result}")
            
            # Check if tool result contains an annotated image
            if isinstance(result, dict) and "image" in result and result["image"] is not None:
                print("🖼️ Using annotated image from tool result")
                self.set_latest_image(result["image"])
            # Check for verification images
            elif isinstance(result, dict) and "verification" in result:
                verification = result["verification"]
                if "combined_image" in verification and verification["combined_image"] is not None:
                    print("🖼️ Using verification comparison image")
                    self.set_latest_image(verification["combined_image"])
                elif "after_image" in verification and verification["after_image"] is not None:
                    print("🖼️ Using after-task image")
                    self.set_latest_image(verification["after_image"])
                else:
                    # Try to capture image after tool execution
                    self.capture_current_image()
            else:
                # Try to capture image after tool execution
                self.capture_current_image()
            
            return result
            
        except json.JSONDecodeError as e:
            error_msg = f"Error parsing tool arguments: {e}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Error executing tool: {e}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

    def _call_llm(self, message: str, image: Optional[MbodiedImage] = None):
        """Call the LLM to get response and tool calls (without executing tools)."""
        try:
            # Capture image if vision-related and no image provided
            if image is None:
                vision_keywords = ["see", "look", "view", "observe", "describe", "what's", "table", "front"]
                if any(keyword in message.lower() for keyword in vision_keywords):
                    print("Vision question detected, capturing current image...")
                    self.capture_current_image()
                    image = self.latest_image

            # Call LLM with tools
            response, tool_calls = self.agent.act(message, image, tools=self.tools)
            
            # Return response and tool_calls (without executing them yet)
            return response, tool_calls

        except Exception as e:
            self._reset_state()
            self.agent = self._create_language_agent()
            print("[ERROR]: resetting agent and state")
            raise LLMError(str(e)) from e
    
    def _execute_tools(self, tool_calls):
        """Execute a list of tool calls and return results."""
        tool_results = []
        for tool_call in tool_calls:
            # Check for interrupt
            if self.interrupt_flag:
                break
                
            result = self._execute_tool_call(tool_call)
            tool_results.append({
                "tool": tool_call.function.name,
                "result": result
            })
        
        return tool_results

    def _generate_contextual_response(self, original_instruction: str, tool_results: List[Dict], image: Optional[MbodiedImage] = None) -> str:
        """Generate a contextual response based on tool execution results."""
        try:
            # Simply pass the raw tool results to the LLM - let it interpret everything
            contextual_prompt = f"""Based on the user's original request: "{original_instruction}"

I executed the following tools with these results:

{json.dumps(tool_results, indent=2, default=str)}

Please provide a natural, conversational response that:
1. Acknowledges what was accomplished based on the tool results
2. Summarizes the key information in a user-friendly way

IMPORTANT: 
- Be conversational and appropriate for speech synthesis
- Interpret the tool results and present the information clearly
- Do NOT add generic endings like "Let me know if you need anything else" or "Is there anything else I can help with"
- Do NOT ask follow-up questions unless directly relevant to the results
- Keep the response focused and complete the task without additional pleasantries"""

            # Generate contextual response using the LLM
            contextual_response = self.agent.act(contextual_prompt, image)
            
            return contextual_response
            
        except Exception as e:
            print(f"Error generating contextual response: {e}")
            # Fallback to basic summary
            if len(tool_results) == 1:
                result = tool_results[0]["result"]
                return result.get("message", "Task completed successfully.")
            else:
                return f"I completed {len(tool_results)} actions for you."

    def get_instruction(self, input_data):
        """Get instruction from text or audio input."""
        if not input_data:
            return "No input provided."
        
        is_audio = isinstance(input_data, str) and os.path.isfile(input_data)
        if is_audio:
            instruction = self.transcribe_audio(input_data)
            if not instruction:
                return "Failed to transcribe audio."
        else:
            instruction = input_data
            
        return instruction, is_audio

    def process_instruction(self, input_data):
        """Single entry point for both text and audio inputs with direct tool calling."""
        
        if not input_data:
            yield "No input provided.", None, None
            return
        
        instruction, is_audio = self.get_instruction(input_data)
        
        if is_audio:
            yield f"Transcribed instruction: {instruction}", None, None

        if instruction.strip().lower() == "exit":
            yield "Exiting the program…", None, None
            return
        
        # Set execution state
        self.is_executing = True
        self.latest_query = instruction
        
        try:
            # Call LLM to get response and tool calls (without executing yet)
            response, tool_calls = self._call_llm(instruction, self.latest_image)

            print(f"🧠 Initial LLM response: '{response}'")
            print(f"🧠 Tool calls to execute: {[tc.function.name for tc in tool_calls] if tool_calls else 'None'}")
            
            # First yield the initial response if it exists
            if response and response.strip():
                print(f"🧠 Yielding initial response: '{response}'")
                audio_initial = self.text_to_speech(response)
                yield response, audio_initial, self.latest_image.pil if self.latest_image else None
            
            # Execute tools if any were requested
            if tool_calls:
                print("🧠 Now executing tools...")
                tool_results = self._execute_tools(tool_calls)
                print(f"🧠 Tool execution completed. Results: {len(tool_results)} tools executed")
                
                # Generate contextual response based on tool results
                print("🧠 Generating contextual response based on tool results...")
                
                try:
                    # Use LLM to generate a contextual response based on tool results
                    final_response = self._generate_contextual_response(
                        instruction, tool_results, self.latest_image
                    )
                        
                except Exception as e:
                    print(f"❌ Error generating contextual response: {e}")
                    # Fallback to original static approach
                    if len(tool_results) == 1:
                        result = tool_results[0]["result"]
                        if result.get("success", True):
                            final_response = result.get("message", "Task completed successfully.")
                        else:
                            final_response = f"I'm sorry, but {result.get('error', 'the operation failed')}."
                    else:
                        final_response = f"I completed {len(tool_results)} actions for you."
                
                # Generate audio for results
                audio = self.text_to_speech(final_response)
                
                # Yield the results response separately
                yield final_response, audio, self.latest_image.pil if self.latest_image else None
            else:
                # No tools to execute, just conversation
                if not (response and response.strip()):
                    # If we haven't yielded anything yet, yield a default response
                    final_response = "I understand your request."
                    audio = self.text_to_speech(final_response)
                    yield final_response, audio, self.latest_image.pil if self.latest_image else None
            
        except LLMError as e:
            msg = f"[LLM ERROR] {e}\nPlease try again."
            audio = self.text_to_speech(msg)
            yield msg, audio, None
            
        except Exception as e:
            msg = f"[ERROR] {str(e)}\nPlease try again."
            audio = self.text_to_speech(msg)
            yield msg, audio, None
            
        finally:
            self.is_executing = False

def start_controllers():
    session_name = "robot_console"
    script_name = "gradio_setup_controllers.sh"
    script_path = PROJECT_ROOT / "scripts" / script_name

    try:
        import subprocess
        # 1. Check if the tmux session already exists
        check_session = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
        
        if check_session.returncode != 0:
            # Session doesn't exist: Open a gnome-terminal running a new tmux session
            # This is the "One-time" window popup
            cmd = ["gnome-terminal", "--", "tmux", "new-session", "-s", session_name, f"bash {script_path}; exec bash"]
            subprocess.Popen(cmd)
            print("Opened new Robot Console window.")
        else:
            # Session exists: Send the script command to the existing tmux session
            # 'C-m' is the tmux way of saying "Press Enter"
            print("Sending 'return home' command to existing window...")
            subprocess.run(["tmux", "send-keys", "-t", session_name, f"bash {script_path}", "C-m"])
        
    except Exception as e:
        print(str(e))


def create_gradio_interface():
    robot = RobotInterface()

    # Custom CSS for blue user messages
    custom_css = """
    /* Gradio 4.x chatbot styling */
    .chatbot .message-wrap.user {
        background-color: #e3f2fd !important;
    }
    .chatbot .message-wrap.user .message {
        color: #1976d2 !important;
    }
    .chatbot .message-wrap.user p {
        color: #1976d2 !important;
    }
    .chatbot .message-wrap.user * {
        color: #1976d2 !important;
    }
    
    /* Alternative selectors for different Gradio versions */
    [data-testid="user"] {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    [data-testid="user"] p {
        color: #1976d2 !important;
    }
    [data-testid="user"] * {
        color: #1976d2 !important;
    }
    
    /* More specific selectors */
    .chatbot .user {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    .chatbot .user p {
        color: #1976d2 !important;
    }
    .chatbot .user div {
        color: #1976d2 !important;
    }
    
    /* Override any orange/default colors */
    .chatbot [data-role="user"] {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    .chatbot [data-role="user"] * {
        color: #1976d2 !important;
    }
    
    /* Aggressive override for all user messages */
    .chatbot div:has([data-testid="user"]) {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    
    /* Force blue for anything that might be user content */
    .chatbot > div > div:first-child {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    
    /* Override default orange/amber colors specifically */
    .chatbot .bg-orange-50,
    .chatbot .bg-amber-50,
    .chatbot .text-orange-600,
    .chatbot .text-amber-600 {
        background-color: #e3f2fd !important;
        color: #1976d2 !important;
    }
    
    /* Change "Send Text" button from orange to blue */
    button[variant="primary"] {
        background-color: #1976d2 !important;
        border-color: #1976d2 !important;
        color: white !important;
    }
    button[variant="primary"]:hover {
        background-color: #1565c0 !important;
        border-color: #1565c0 !important;
    }
    button[variant="primary"]:active {
        background-color: #0d47a1 !important;
        border-color: #0d47a1 !important;
    }
    
    /* Alternative selectors for buttons */
    .gr-button-primary {
        background-color: #1976d2 !important;
        border-color: #1976d2 !important;
        color: white !important;
    }
    .gr-button-primary:hover {
        background-color: #1565c0 !important;
        border-color: #1565c0 !important;
    }
    .gr-button-primary:active {
        background-color: #0d47a1 !important;
        border-color: #0d47a1 !important;
    }
    
    /* More specific button targeting */
    .gradio-container button.primary,
    .gradio-container .primary {
        background-color: #1976d2 !important;
        border-color: #1976d2 !important;
        color: white !important;
    }
    
    /* Force camera images to fill their containers */
    .gradio-image img {
        width: 100% !important;
        height: 100% !important;
        object-fit: cover !important;
    }
    
    /* Ensure image containers are properly sized */
    .gradio-image {
        width: 100% !important;
        height: 600px !important;
    }
    
    /* Remove any padding/margins that create white space */
    .gradio-image .image-container {
        padding: 0 !important;
        margin: 0 !important;
    }
    """

    with gr.Blocks(title="HRC DS-RFM Demo Interface") as demo:
        # Inject custom CSS using HTML component
        gr.HTML(f"<style>{custom_css}</style>")
        
        with gr.Row():
            with gr.Column(scale=1, min_width=60):
                gr.Image("assets/images/A-STAR_LOGO.png", height=50, width=50, show_label=False, container=False, 
                         buttons=[])
            with gr.Column(scale=10):
                gr.Markdown("## HRC DS-RFM Demo Interface")
        #gr.Markdown("**Advanced robot assistant with direct LLM tool calling and immediate execution**")
        #gr.Markdown("*Powered by `system_prompt_tool_calling.txt`*")

        with gr.Tabs():
            # ===== Voice Chat (Streaming) UI =====
            with gr.TabItem("Voice Chat (Streaming)"):
                with gr.Row():
                    with gr.Column():
                        # Text input section
                        gr.Markdown("### Text Input")
                        stream_txt_in = gr.Textbox(
                            label="Type your message", 
                            placeholder="Type here or use voice input below...",
                            lines=2
                        )
                        with gr.Row():
                            submit_stream_txt = gr.Button("Submit", variant="primary")
                            clear_stream_txt = gr.Button("Clear")
                        
                        # Voice input section
                        gr.Markdown("### Voice Input")
                        input_audio_stream = gr.Audio(
                            label="Streaming Voice Input", sources="microphone", type="numpy"
                        )
                        
                        # Live Camera Stream section
                        gr.Markdown("### Live Camera Stream")
                        gr.Markdown("*Real-time raw camera feed from Isaac Sim*")
                        with gr.Row():
                            with gr.Column(scale=4):
                                stream_img_out = gr.Image(
                                    label="Live Robot Camera", 
                                    width=800, 
                                    height=600,
                                    interactive=False,
                                    buttons=[],
                                    container=False,
                                    show_label=True
                                )
                            with gr.Column(scale=1):
                                camera_status = gr.Textbox(
                                    label="Camera Status",
                                    value="Initializing...",
                                    interactive=False,
                                    lines=2
                                )
                                refresh_camera = gr.Button("🔄 Refresh", variant="secondary", size="sm")
                        
                    with gr.Column():
                        chatbot_stream = gr.Chatbot(label="Conversation")
                        output_audio_stream = gr.Audio(
                            label="Output Audio", streaming=True, autoplay=True
                        )
                        
                        # Detected Objects section - moved here under audio output
                        gr.Markdown("### Detected Objects & Analysis")
                        gr.Markdown("*Annotated results from robot vision tools*")
                        detected_objects_img = gr.Image(
                            label="Detected Objects & Analysis Results", 
                            width=600, 
                            height=350,
                            interactive=False
                        )

                # Local helpers to use the LLM agent for listen-and-speak
                def voicechat_process_audio_local(audio: tuple[int, np.ndarray], state: VoiceChatState):
                    sampling_rate, chunk = audio
                    if state.stream is None:
                        state.stream = chunk
                        state.sampling_rate = sampling_rate
                    else:
                        state.stream = np.concatenate((state.stream, chunk))

                    pause_detected, started_talking = determine_pause(
                        state.stream, state.sampling_rate, state
                    )
                    state.pause_detected = pause_detected
                    state.started_talking = started_talking

                    if state.pause_detected and state.started_talking:
                        return gr.Audio(recording=False), state
                    return None, state

                def _chunk_bytes(data: bytes, chunk_size: int = 32_000):
                    for start in range(0, len(data), chunk_size):
                        yield data[start: start + chunk_size]

                def voicechat_response_local(state: VoiceChatState):
                    # No speech captured
                    if not state.pause_detected and not state.started_talking:
                        return None, VoiceChatState()

                    # Serialize user's captured stream to WAV bytes
                    wav_buf = io.BytesIO()
                    segment = AudioSegment(
                        state.stream.tobytes(),
                        frame_rate=state.sampling_rate,
                        sample_width=state.stream.dtype.itemsize,
                        channels=(1 if len(state.stream.shape) == 1 else state.stream.shape[1]),
                    )
                    segment.export(wav_buf, format="wav")

                    # Persist temp WAV file for transcription
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(wav_buf.getvalue())
                        user_audio_path = f.name

                    # Transcribe and display user's text
                    try:
                        transcription = robot.transcribe_audio(user_audio_path)
                    except Exception:
                        transcription = ""

                    if not transcription:
                        transcription = "[Unintelligible / empty]"

                    state.conversation.append({"role": "user", "content": transcription})

                    # Call LLM agent to generate assistant response using robot's process_instruction
                    try:
                        # Use the robot's existing tool calling pipeline
                        response, tool_calls = robot._call_llm(transcription, robot.latest_image)
                        
                        print(f"🧠 [Voice Chat] Initial LLM response: '{response}'")
                        print(f"🧠 [Voice Chat] Tool calls: {[tc.function.name for tc in tool_calls] if tool_calls else 'None'}")
                        
                        # Execute tools if any were requested
                        tool_results = []
                        if tool_calls:
                            tool_results = robot._execute_tools(tool_calls)
                            print(f"🧠 [Voice Chat] Tool execution completed: {len(tool_results)} tools executed")
                        
                        # Get current image for display - keep detected objects separate from live stream
                        current_image = robot.latest_image.pil if robot.latest_image else None
                        
                        # Get live camera frame (raw feed for streaming display)
                        live_frame = robot.get_live_camera_frame()
                        
                        # For streaming output, prioritize live camera feed (not detected objects)
                        display_image = live_frame if live_frame else current_image
                        
                        # First stream the initial response if it exists
                        if response and response.strip():
                            print(f"🧠 [Voice Stream] Streaming initial response: '{response}'")
                            
                            # Add initial response to conversation BEFORE streaming
                            state.conversation.append({"role": "assistant", "content": response})
                            
                            tts_initial = robot.text_to_speech(response)
                            if tts_initial and tts_initial.lower().endswith(".mp3"):
                                with open(tts_initial, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield mp3_chunk, state, display_image, state.conversation
                        
                        # Generate contextual response based on tool results if tools were executed
                        if tool_results:
                            print(f"🧠 [Voice Stream] Streaming tool results...")
                            try:
                                results_text = robot._generate_contextual_response(
                                    transcription, tool_results, robot.latest_image
                                )
                            except Exception as e:
                                print(f"❌ Error generating contextual response: {e}")
                                # Fallback to basic response
                                if len(tool_results) == 1:
                                    result = tool_results[0]["result"]
                                    if result.get("success", True):
                                        results_text = result.get("message", "Task completed successfully.")
                                    else:
                                        results_text = f"I'm sorry, but {result.get('error', 'the operation failed')}."
                                else:
                                    results_text = f"I completed {len(tool_results)} actions for you."
                            
                            # Stream the results audio
                            tts_results = robot.text_to_speech(results_text)
                            if tts_results and tts_results.lower().endswith(".mp3"):
                                with open(tts_results, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield mp3_chunk, state, display_image, state.conversation
                            else:
                                # Fallback: stream silence if TTS failed
                                silence = AudioSegment.silent(duration=300)
                                out = io.BytesIO()
                                silence.export(out, format="mp3", bitrate="64k")
                                for mp3_chunk in _chunk_bytes(out.getvalue()):
                                    yield mp3_chunk, state, display_image, state.conversation
                            
                            # Add results to conversation
                            state.conversation.append({"role": "assistant", "content": results_text})
                        elif not (response and response.strip()):
                            # No initial response and no tools - provide default
                            default_text = "I understand your request."
                            tts_default = robot.text_to_speech(default_text)
                            if tts_default and tts_default.lower().endswith(".mp3"):
                                with open(tts_default, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield mp3_chunk, state, display_image, state.conversation
                            state.conversation.append({"role": "assistant", "content": default_text})
                            
                    except Exception as e:
                        error_text = f"[LLM ERROR] {e}"
                        print(f"❌ Voice streaming error: {error_text}")
                        tts_error = robot.text_to_speech(error_text)
                        if tts_error and tts_error.lower().endswith(".mp3"):
                            with open(tts_error, "rb") as rf:
                                for mp3_chunk in _chunk_bytes(rf.read()):
                                    yield mp3_chunk, state, display_image, state.conversation
                        state.conversation.append({"role": "assistant", "content": error_text})

                    # Reset streaming state
                    yield None, VoiceChatState(conversation=state.conversation), display_image, state.conversation

                def voicechat_start_recording_user_local(state: VoiceChatState):
                    if not state.stopped:
                        return gr.Audio(recording=True)
                    return gr.Audio(recording=False)

                stream_state = gr.State(value=VoiceChatState())

                stream_evt = input_audio_stream.stream(
                    fn=voicechat_process_audio_local,
                    inputs=[input_audio_stream, stream_state],
                    outputs=[input_audio_stream, stream_state],
                    stream_every=0.5,
                    time_limit=30,
                )

                respond_evt = input_audio_stream.stop_recording(
                    fn=voicechat_response_local,
                    inputs=[stream_state],
                    outputs=[output_audio_stream, stream_state, stream_img_out, chatbot_stream],
                )

                restart_evt = output_audio_stream.stop(
                    fn=voicechat_start_recording_user_local,
                    inputs=[stream_state],
                    outputs=[input_audio_stream],
                )

                cancel_stream = gr.Button("Stop Conversation", variant="stop")
                cancel_stream.click(
                    lambda: (VoiceChatState(stopped=True), gr.Audio(recording=False)),
                    None,
                    [stream_state, input_audio_stream],
                    cancels=[respond_evt, restart_evt, stream_evt],
                )

                # Text input handler for streaming conversation
                def handle_text_input_stream(text_input, state: VoiceChatState):
                    if not text_input.strip():
                        return "", state
                    
                    # Add user text to conversation
                    state.conversation.append({"role": "user", "content": text_input})
                    
                    # Call LLM agent to generate assistant response
                    try:
                        # Use the robot's existing tool calling pipeline
                        response, tool_calls = robot._call_llm(text_input, robot.latest_image)
                        
                        print(f"🧠 [Stream Text] Initial LLM response: '{response}'")
                        print(f"🧠 [Stream Text] Tool calls: {[tc.function.name for tc in tool_calls] if tool_calls else 'None'}")
                        
                        # Execute tools if any were requested
                        tool_results = []
                        if tool_calls:
                            tool_results = robot._execute_tools(tool_calls)
                            print(f"🧠 [Stream Text] Tool execution completed: {len(tool_results)} tools executed")
                        
                        # Generate contextual response based on tool results if tools were executed
                        if tool_results:
                            try:
                                assistant_text = robot._generate_contextual_response(
                                    text_input, tool_results, robot.latest_image
                                )
                                # If initial LLM response exists, prepend it
                                if response and response.strip():
                                    print(f"🧠 [Stream] Prepending initial response: '{response}'")
                                    assistant_text = f"{response}\n\n{assistant_text}"
                                else:
                                    print(f"🧠 [Stream] No initial response to prepend (response: '{response}')")
                            except Exception as e:
                                print(f"❌ Error generating contextual response: {e}")
                                # Fallback to basic response
                                if len(tool_results) == 1:
                                    result = tool_results[0]["result"]
                                    if result.get("success", True):
                                        assistant_text = result.get("message", "Task completed successfully.")
                                    else:
                                        assistant_text = f"I'm sorry, but {result.get('error', 'the operation failed')}."
                                else:
                                    assistant_text = f"I completed {len(tool_results)} actions for you."
                        else:
                            # No tools executed, just conversation
                            assistant_text = response if response else "I understand your request."
                            
                    except Exception as e:
                        assistant_text = f"[LLM ERROR] {e}"
                    
                    # Add assistant response to conversation
                    state.conversation.append({"role": "assistant", "content": assistant_text})
                    
                    # Generate TTS for the response
                    tts_path = robot.text_to_speech(assistant_text)
                    
                    return "", state  # Clear input and return updated state

                def handle_text_input_with_audio_stream(text_input, state: VoiceChatState):
                    if not text_input.strip():
                        return "", None, state, state.conversation
                    
                    # Add user text to conversation
                    state.conversation.append({"role": "user", "content": text_input})
                    
                    # Call LLM agent to generate assistant response
                    try:
                        # Use the robot's existing tool calling pipeline
                        response, tool_calls = robot._call_llm(text_input, robot.latest_image)
                        
                        print(f"🧠 [Stream Text] Initial LLM response: '{response}'")
                        print(f"🧠 [Stream Text] Tool calls: {[tc.function.name for tc in tool_calls] if tool_calls else 'None'}")
                        
                        # Execute tools if any were requested
                        tool_results = []
                        if tool_calls:
                            tool_results = robot._execute_tools(tool_calls)
                            print(f"🧠 [Stream Text] Tool execution completed: {len(tool_results)} tools executed")
                        
                        # Don't update live camera on submit - it should update independently
                        # Only update detected objects if vision tools were used
                        display_image = None
                        if tool_calls and any("vision" in tc.function.name.lower() or "detect" in tc.function.name.lower() or "image" in tc.function.name.lower() for tc in tool_calls):
                            # Only update detected objects display if vision tools were used
                            display_image = robot.latest_image.pil if robot.latest_image else None
                        
                        # First stream the initial response if it exists
                        if response and response.strip():
                            print(f"🧠 [Stream Text Audio] Streaming initial response: '{response}'")
                            
                            # Add initial response to conversation BEFORE streaming
                            state.conversation.append({"role": "assistant", "content": response})
                            
                            tts_initial = robot.text_to_speech(response)
                            if tts_initial and tts_initial.lower().endswith(".mp3"):
                                with open(tts_initial, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield "", mp3_chunk, state, state.conversation
                        
                        # Generate contextual response based on tool results if tools were executed
                        if tool_results:
                            print(f"🧠 [Stream Text Audio] Streaming tool results...")
                            try:
                                results_text = robot._generate_contextual_response(
                                    text_input, tool_results, robot.latest_image
                                )
                            except Exception as e:
                                print(f"❌ Error generating contextual response: {e}")
                                # Fallback to basic response
                                if len(tool_results) == 1:
                                    result = tool_results[0]["result"]
                                    if result.get("success", True):
                                        results_text = result.get("message", "Task completed successfully.")
                                    else:
                                        results_text = f"I'm sorry, but {result.get('error', 'the operation failed')}."
                                else:
                                    results_text = f"I completed {len(tool_results)} actions for you."
                            
                            # Stream the results audio
                            tts_results = robot.text_to_speech(results_text)
                            if tts_results and tts_results.lower().endswith(".mp3"):
                                with open(tts_results, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield "", mp3_chunk, state, state.conversation
                            else:
                                # Fallback: stream silence if TTS failed
                                silence = AudioSegment.silent(duration=300)
                                out = io.BytesIO()
                                silence.export(out, format="mp3", bitrate="64k")
                                for mp3_chunk in _chunk_bytes(out.getvalue()):
                                    yield "", mp3_chunk, state, state.conversation
                            
                            # Add results to conversation
                            state.conversation.append({"role": "assistant", "content": results_text})
                        elif not (response and response.strip()):
                            # No initial response and no tools - provide default
                            default_text = "I understand your request."
                            tts_default = robot.text_to_speech(default_text)
                            if tts_default and tts_default.lower().endswith(".mp3"):
                                with open(tts_default, "rb") as rf:
                                    for mp3_chunk in _chunk_bytes(rf.read()):
                                        yield "", mp3_chunk, state, state.conversation
                            state.conversation.append({"role": "assistant", "content": default_text})
                            
                    except Exception as e:
                        error_text = f"[LLM ERROR] {e}"
                        print(f"❌ Stream text audio error: {error_text}")
                        tts_error = robot.text_to_speech(error_text)
                        if tts_error and tts_error.lower().endswith(".mp3"):
                            with open(tts_error, "rb") as rf:
                                for mp3_chunk in _chunk_bytes(rf.read()):
                                    yield "", mp3_chunk, state, state.conversation
                        state.conversation.append({"role": "assistant", "content": error_text})
                    
                    # Final yield to clear input and stop audio stream
                    yield "", None, state, state.conversation

                # Event handlers for text input
                submit_stream_txt.click(
                    handle_text_input_with_audio_stream,
                    inputs=[stream_txt_in, stream_state],
                    outputs=[stream_txt_in, output_audio_stream, stream_state, chatbot_stream]
                )

                stream_txt_in.submit(
                    handle_text_input_with_audio_stream,
                    inputs=[stream_txt_in, stream_state],
                    outputs=[stream_txt_in, output_audio_stream, stream_state, chatbot_stream]
                )

                clear_stream_txt.click(
                    lambda: "",
                    outputs=[stream_txt_in]
                )

                # Live camera update functions
                def update_live_camera():
                    """Update only the live camera display (raw feed)."""
                    live_frame = robot.get_live_camera_frame()
                    status = robot.get_camera_status()
                    return live_frame, status

                def update_detected_objects():
                    """Update only the detected objects display (annotated results)."""
                    # This shows the processed/annotated image from robot tools
                    detected_frame = robot.latest_image.pil if robot.latest_image else None
                    return detected_frame

                def refresh_camera_manual():
                    """Manually refresh camera displays."""
                    live_frame = robot.get_live_camera_frame()
                    detected_frame = robot.latest_image.pil if robot.latest_image else None
                    status = robot.get_camera_status()
                    return live_frame, detected_frame, status

                # Camera event handlers
                refresh_camera.click(
                    refresh_camera_manual,
                    outputs=[stream_img_out, detected_objects_img, camera_status]
                )

                # Auto-refresh live camera every 0.5 seconds for smooth streaming
                live_camera_timer = gr.Timer(0.5)
                live_camera_timer.tick(
                    fn=update_live_camera,
                    outputs=[stream_img_out, camera_status]
                )

                # Update detected objects only when robot tools are executed (less frequent)
                detected_objects_timer = gr.Timer(2.0)
                detected_objects_timer.tick(
                    fn=update_detected_objects,
                    outputs=[detected_objects_img]
                )

            with gr.TabItem("Voice Input"):
                with gr.Row():
                    with gr.Column(scale=1):
                        mic_in = gr.Audio(sources="microphone",
                                          type="filepath",
                                          label="Speak your instruction")
                        with gr.Row():
                            submit_mic = gr.Button("Submit", variant="primary")
                            clear_mic = gr.Button("Clear")
                        mic_img = gr.Image(label="Robot Camera", width=800, height=600)

                    with gr.Column(scale=1):
                        mic_txt = gr.Textbox(label="Response", lines=12)
                        mic_aud = gr.Audio(label="Speech",
                                           type="filepath",
                                           autoplay=True)

        
        # Bottom row
        with gr.Row():
            interrupt_btn = gr.Button("Interrupt Current Operation", variant="stop")
            interrupt_note = gr.Markdown("")
        
        # Event handlers
        submit_mic.click(
            robot.process_instruction,
            inputs=mic_in,
            outputs=[mic_txt, mic_aud, mic_img]
        ).then(
            lambda: "", None, interrupt_note
        ).then(
            lambda: None, None, mic_in
        )

        clear_mic.click(lambda: ("", None, None, None),
                        inputs=None,
                        outputs=[mic_in, mic_txt, mic_aud, mic_img]) \
                .then(lambda: "", None, interrupt_note)


        
        # (Removed Streaming Voice Chat event handlers)
        
        # Interrupt handler
        interrupt_btn.click(robot.interrupt_plan, outputs=interrupt_note)

    return demo


if __name__ == "__main__":
    try:
        # Initialize ROS for camera system (needed before preloading)
        if not rclpy.ok():
            rclpy.init()
        
        # Pre-load all controllers at startup for fastest tool execution
        # This avoids action server discovery delays and ROS2 node conflicts
        #preload_all_controllers(discover_arm_server=args.discover_arm_server)

        # launch controllers in tmux
        start_controllers()

        # TODO: dont hardcode the image provider preload and previous controller preload
        from robot_tools import preload_image_provider
        preload_image_provider()
        
        
        # Pre-load VLA policy if requested
        if args.preload_policy:
            from robot_tools import preload_vla_policy
            preload_vla_policy()

        interface = create_gradio_interface()
        interface.launch(server_name="0.0.0.0", server_port=7868, share=True)
    finally:
        # Clean up ROS nodes
        if rclpy.ok():
            rclpy.shutdown()

