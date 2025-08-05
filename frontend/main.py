import asyncio
import streamlit as st
from chatbot import Chatbot


async def main():
    """Main function to run the Streamlit app"""
    
    # Initialize session state
    if "server_connected" not in st.session_state:
        st.session_state["server_connected"] = False

    if "tools" not in st.session_state:
        st.session_state["tools"] = []
        
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
        
    # API configuration
    API_URL = "http://localhost:8000"

    # Set page config
    st.set_page_config(
        page_title="MCP Chatbot Client", 
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Create and render chatbot
    chatbot = Chatbot(API_URL)
    await chatbot.render()


if __name__ == "__main__":
    # Note: In Streamlit, we can't use asyncio.run() directly
    # Instead, we'll use Streamlit's async support
    try:
        asyncio.run(main())
    except RuntimeError:
        # If there's already an event loop running (common in Streamlit Cloud)
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.run(main())