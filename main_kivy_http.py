import kivy
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock
import threading
import requests
import json
from dataclasses import dataclass
from typing import Optional

kivy.require('2.3.0')

@dataclass
class Video:
    id: int
    title: str
    author: str
    status: str
    transcript: str
    summary1: str
    summary2: str
    summary3: str
    link: str
    thumbnail_url: str

class TursoHTTPClient:
    """HTTP client for Turso database - works on Android"""
    def __init__(self, url, auth_token):
        self.url = url
        self.auth_token = auth_token
        self.headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
    
    def execute_query(self, sql, params=None):
        """Execute SQL query via HTTP API"""
        try:
            data = {
                'requests': [{
                    'type': 'execute',
                    'stmt': {
                        'sql': sql,
                        'args': params or []
                    }
                }]
            }
            
            response = requests.post(
                f"{self.url}/v2/pipeline",
                headers=self.headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'results' in result and len(result['results']) > 0:
                    return result['results'][0]
            return None
            
        except Exception as e:
            print(f"HTTP query error: {e}")
            return None

class MainScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.name = 'main'
        self.db_client = TursoHTTPClient(
            url="https://yttrans-saoumfa.aws-eu-west-1.turso.io",
            auth_token="eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJnaWQiOiI0OWIxZDA1MS02ZWU2LTRlNDYtYjQ0YS05MzJmMzNlZGRhNTEiLCJpYXQiOjE3NjUwNzgzMTMsInJpZCI6IjI0MjI2YWI3LTgyOGMtNDg1YS04MmE5LTljZjc0MjMxM2VlZCJ9.bGPjz-E368-xS0PtmBhPn-40lAEY7-iNUXAZER5E9pRwoymdIdcqcDkPFICaRzb45LgxCO__hXqxJGSNteY-Aw"
        )
        self.setup_ui()
    
    def setup_ui(self):
        # Main layout
        layout = BoxLayout(orientation='vertical')
        
        # Scrollable video list
        scroll = ScrollView()
        self.video_list_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.video_list_layout.bind(minimum_height=self.video_list_layout.setter('height'))
        
        scroll.add_widget(self.video_list_layout)
        layout.add_widget(scroll)
        
        self.add_widget(layout)
        
        # Load data after UI is ready
        Clock.schedule_once(lambda dt: self.load_database_data(), 0.5)
    
    def load_database_data(self):
        # Show loading status
        loading_label = Label(text='Loading database...', size_hint_y=None, height=50)
        self.video_list_layout.add_widget(loading_label)
        
        # Load data in background thread
        thread = threading.Thread(target=self.load_videos_from_db)
        thread.daemon = True
        thread.start()
    
    def load_videos_from_db(self):
        try:
            # Try full query first
            result = self.db_client.execute_query(
                "SELECT ID, Title, Author, Status, Transcript, Summary1, Summary2, Summary3, Link FROM Youtube_Summaries ORDER BY ID DESC"
            )
            
            if not result:
                # Fallback to basic columns
                result = self.db_client.execute_query(
                    "SELECT ID, Title, Author, Status, Transcript, Link FROM Youtube_Summaries ORDER BY ID DESC"
                )
            
            videos = []
            if result and 'results' in result and len(result['results']) > 0:
                response_result = result['results'][0]['response']['result']
                if 'rows' in response_result:
                    for row in response_result['rows']:
                        # Extract values from nested objects
                        values = []
                        for cell in row:
                            if 'value' in cell:
                                values.append(cell['value'])
                            else:
                                values.append(None)
                        
                        if len(values) >= 7:
                            video = Video(
                                id=values[0],
                                title=values[1] or "No Title",
                                author=values[2] or "No Author",
                                status=values[3] or "Unknown",
                                transcript=values[4] or "",
                                summary1=values[5] or "",
                                summary2=values[6] or "",
                                summary3=values[7] if len(values) > 7 else "",
                                link=values[8] if len(values) > 8 else (values[5] if len(values) == 6 else ""),
                                thumbnail_url=""
                            )
                        else:
                            video = Video(
                                id=values[0],
                                title=values[1] or "No Title",
                                author=values[2] or "No Author",
                                status=values[3] or "Unknown",
                                transcript=values[4] or "",
                                summary1="",
                                summary2="",
                                summary3="",
                                link=values[5] if len(values) > 5 else "",
                                thumbnail_url=""
                            )
                        videos.append(video)
            
            result_data = {"success": True, "videos": videos}
            
        except Exception as e:
            result_data = {"success": False, "error": str(e)}
        
        # Update UI from main thread
        Clock.schedule_once(lambda dt: self.populate_ui_with_data(result_data), 0)
    
    def populate_ui_with_data(self, result):
        # Clear loading label
        self.video_list_layout.clear_widgets()
        
        if not result["success"]:
            error_label = Label(text=f"Error: {result['error']}", size_hint_y=None, height=50)
            self.video_list_layout.add_widget(error_label)
            return
        
        self.app_ref.videos = result["videos"]
        
        if not self.app_ref.videos:
            no_data_label = Label(text="No videos found", size_hint_y=None, height=50)
            self.video_list_layout.add_widget(no_data_label)
            return
        
        # Create video rows
        for video in self.app_ref.videos:
            self.create_video_row(video)
    
    def create_video_row(self, video: Video):
        row_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=120, spacing=5)
        
        # Delete button
        delete_btn = Button(text='🗑', size_hint_x=None, width=50, background_color=(1, 0, 0, 1))
        delete_btn.bind(on_press=lambda btn, v=video: self.delete_video(v))
        row_layout.add_widget(delete_btn)
        
        # Thumbnail placeholder
        thumbnail_label = Label(text='📹', size_hint_x=None, width=80)
        row_layout.add_widget(thumbnail_label)
        
        # Text field (clickable)
        text_layout = BoxLayout(orientation='vertical')
        
        author_label = Label(text=video.author, font_size='14sp', halign='left')
        title_label = Label(text=video.title, font_size='16sp', bold=True, halign='left', text_size=(250, None))
        
        # Make text clickable
        for label in [author_label, title_label]:
            label.bind(on_touch_down=lambda lbl, touch, v=video: self.on_video_click(v) if lbl.collide_point(*touch.pos) else False)
        
        text_layout.add_widget(author_label)
        text_layout.add_widget(title_label)
        row_layout.add_widget(text_layout)
        
        self.video_list_layout.add_widget(row_layout)
    
    def on_video_click(self, video: Video):
        self.app_ref.show_detail_screen(video)
    
    def delete_video(self, video: Video):
        # Delete from database in background
        thread = threading.Thread(target=self.delete_video_from_db, args=(video,))
        thread.daemon = True
        thread.start()
    
    def delete_video_from_db(self, video: Video):
        try:
            result = self.db_client.execute_query(
                "DELETE FROM Youtube_Summaries WHERE ID = ?",
                [video.id]
            )
            
            if result:
                result_data = {"success": True}
            else:
                result_data = {"success": False, "error": "Delete failed"}
                
        except Exception as e:
            result_data = {"success": False, "error": str(e)}
        
        # Update UI from main thread
        Clock.schedule_once(lambda dt: self.handle_delete_result(result_data, video), 0)
    
    def handle_delete_result(self, result, video: Video):
        if result["success"]:
            # Remove from memory and UI
            self.app_ref.videos = [v for v in self.app_ref.videos if v.id != video.id]
            self.populate_ui_with_data({"success": True, "videos": self.app_ref.videos})
            print("Video deleted successfully")
        else:
            print(f"Failed to delete video: {result['error']}")

class DetailScreen(Screen):
    def __init__(self, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref
        self.name = 'detail'
        self.setup_ui()
    
    def setup_ui(self):
        # Main layout
        layout = BoxLayout(orientation='vertical')
        
        # Button row
        button_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=5)
        
        # Back button
        self.back_btn = Button(text='← Back', size_hint_x=None, width=100)
        self.back_btn.bind(on_press=lambda btn: self.app_ref.show_main_screen())
        button_layout.add_widget(self.back_btn)
        
        # Summary buttons
        self.summary1_btn = Button(text='Summary 1', size_hint_x=None, width=100)
        self.summary1_btn.bind(on_press=lambda btn: self.show_summary(1))
        button_layout.add_widget(self.summary1_btn)
        
        self.summary2_btn = Button(text='Summary 2', size_hint_x=None, width=100)
        self.summary2_btn.bind(on_press=lambda btn: self.show_summary(2))
        button_layout.add_widget(self.summary2_btn)
        
        self.summary3_btn = Button(text='Summary 3', size_hint_x=None, width=100)
        self.summary3_btn.bind(on_press=lambda btn: self.show_summary(3))
        button_layout.add_widget(self.summary3_btn)
        
        layout.add_widget(button_layout)
        
        # Video info
        self.video_title_label = Label(text='', font_size='18sp', bold=True, text_size=(380, None), size_hint_y=None, height=60)
        layout.add_widget(self.video_title_label)
        
        self.video_author_label = Label(text='', font_size='14sp', text_size=(380, None), size_hint_y=None, height=40)
        layout.add_widget(self.video_author_label)
        
        # Summary text
        self.summary_label = Label(text='', font_size='14sp', text_size=(380, None), valign='top')
        layout.add_widget(self.summary_label)
        
        self.add_widget(layout)
    
    def update_video_info(self, video: Video):
        self.app_ref.current_video = video
        self.video_title_label.text = video.title
        self.video_author_label.text = f"By: {video.author}"
        
        # Show summary 1 by default
        self.show_summary(1)
    
    def show_summary(self, summary_num: int):
        if not self.app_ref.current_video:
            return
        
        # Update button states (visual feedback)
        self.summary1_btn.background_color = (0.2, 0.6, 1, 1) if summary_num == 1 else (0.2, 0.2, 0.2, 1)
        self.summary2_btn.background_color = (0.2, 0.6, 1, 1) if summary_num == 2 else (0.2, 0.2, 0.2, 1)
        self.summary3_btn.background_color = (0.2, 0.6, 1, 1) if summary_num == 3 else (0.2, 0.2, 0.2, 1)
        
        # Show summary text
        summary_text = ""
        if summary_num == 1:
            summary_text = self.app_ref.current_video.summary1 or "No summary available"
        elif summary_num == 2:
            summary_text = self.app_ref.current_video.summary2 or "No summary available"
        elif summary_num == 3:
            summary_text = self.app_ref.current_video.summary3 or "No summary available"
        
        self.summary_label.text = summary_text

class YouTubeSummaryApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.videos: list[Video] = []
        self.current_video: Optional[Video] = None
    
    def build(self):
        # Create screen manager
        sm = ScreenManager()
        
        # Create screens
        self.main_screen = MainScreen(self)
        self.detail_screen = DetailScreen(self)
        
        # Add screens to manager
        sm.add_widget(self.main_screen)
        sm.add_widget(self.detail_screen)
        
        return sm
    
    def show_main_screen(self):
        self.root.current = 'main'
    
    def show_detail_screen(self, video: Video):
        self.detail_screen.update_video_info(video)
        self.root.current = 'detail'

if __name__ == '__main__':
    YouTubeSummaryApp().run()
