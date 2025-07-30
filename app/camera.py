"""
Camera interface for plant monitoring and visual analysis
"""

import cv2
import logging
import numpy as np
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

class CameraInterface:
    """Handles camera capture and basic image analysis"""
    
    def __init__(self, mock: bool = False, camera_index: int = 0):
        self.mock = mock or not self._camera_available()
        self.logger = logging.getLogger(__name__)
        self.camera_index = camera_index
        self.cap = None
        
        # Image storage paths
        self.image_path = Path("~/hydro/images").expanduser()
        self.image_path.mkdir(parents=True, exist_ok=True)
        
        if not self.mock:
            self._init_camera()
        else:
            self.logger.info("Running camera in mock mode")
    
    def _camera_available(self) -> bool:
        """Check if camera hardware is available"""
        try:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.release()
                return True
            return False
        except Exception:
            return False
    
    def _init_camera(self):
        """Initialize camera hardware"""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            
            if not self.cap.isOpened():
                self.logger.error("Failed to open camera")
                self.mock = True
                return
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            self.logger.info("Camera initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Camera initialization failed: {e}")
            self.mock = True
    
    async def capture_image(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """Capture image and save to disk"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"plant_{timestamp}.jpg"
        
        image_file = self.image_path / filename
        
        if self.mock:
            # Generate mock image
            mock_image = self._generate_mock_image()
            cv2.imwrite(str(image_file), mock_image)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "filename": filename,
                "filepath": str(image_file),
                "mock": True,
                "analysis": self._mock_image_analysis()
            }
        
        try:
            # Capture frame
            ret, frame = self.cap.read()
            
            if not ret:
                raise Exception("Failed to capture frame")
            
            # Save image
            cv2.imwrite(str(image_file), frame)
            
            # Basic analysis
            analysis = self._analyze_image(frame)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "filename": filename,
                "filepath": str(image_file),
                "mock": False,
                "analysis": analysis
            }
            
        except Exception as e:
            self.logger.error(f"Image capture failed: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _analyze_image(self, image: np.ndarray) -> Dict[str, Any]:
        """Perform basic image analysis"""
        try:
            # Convert to different color spaces
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            
            # Calculate basic statistics
            height, width = image.shape[:2]
            
            # Green detection (for plant health)
            green_mask = cv2.inRange(hsv, (40, 50, 50), (80, 255, 255))
            green_pixels = cv2.countNonZero(green_mask)
            green_percentage = (green_pixels / (height * width)) * 100
            
            # Brown/yellow detection (potential issues)
            brown_mask = cv2.inRange(hsv, (10, 50, 50), (30, 255, 200))
            brown_pixels = cv2.countNonZero(brown_mask)
            brown_percentage = (brown_pixels / (height * width)) * 100
            
            # Overall brightness
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            
            # Color distribution
            b_mean, g_mean, r_mean = cv2.mean(image)[:3]
            
            return {
                "dimensions": {"width": width, "height": height},
                "green_coverage_percent": round(green_percentage, 2),
                "brown_coverage_percent": round(brown_percentage, 2),
                "brightness": round(brightness, 1),
                "color_means": {
                    "blue": round(b_mean, 1),
                    "green": round(g_mean, 1),
                    "red": round(r_mean, 1)
                },
                "health_indicators": {
                    "green_healthy": green_percentage > 15,
                    "brown_stress": brown_percentage > 5,
                    "adequate_light": brightness > 80
                }
            }
            
        except Exception as e:
            self.logger.error(f"Image analysis failed: {e}")
            return {"error": str(e)}
    
    def _generate_mock_image(self) -> np.ndarray:
        """Generate a mock plant image for testing"""
        # Create a 1920x1080 image
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # Fill with soil-colored background
        image[:, :] = (101, 67, 33)  # Brown soil color
        
        # Add some green "plants"
        for i in range(5):
            x = np.random.randint(200, 1720)
            y = np.random.randint(200, 880)
            
            # Draw green ellipse for plant
            cv2.ellipse(image, (x, y), (50, 80), 0, 0, 360, (34, 139, 34), -1)
            
            # Add some leaves
            for j in range(3):
                leaf_x = x + np.random.randint(-40, 40)
                leaf_y = y + np.random.randint(-60, 20)
                cv2.ellipse(image, (leaf_x, leaf_y), (15, 25), 
                           np.random.randint(0, 360), 0, 360, (50, 205, 50), -1)
        
        # Add some noise for realism
        noise = np.random.randint(0, 30, image.shape, dtype=np.uint8)
        image = cv2.add(image, noise)
        
        return image
    
    def _mock_image_analysis(self) -> Dict[str, Any]:
        """Generate mock image analysis data"""
        return {
            "dimensions": {"width": 1920, "height": 1080},
            "green_coverage_percent": round(np.random.uniform(20, 40), 2),
            "brown_coverage_percent": round(np.random.uniform(1, 3), 2),
            "brightness": round(np.random.uniform(90, 120), 1),
            "color_means": {
                "blue": round(np.random.uniform(60, 80), 1),
                "green": round(np.random.uniform(80, 120), 1),
                "red": round(np.random.uniform(70, 90), 1)
            },
            "health_indicators": {
                "green_healthy": True,
                "brown_stress": False,
                "adequate_light": True
            }
        }
    
    async def time_lapse_capture(self, interval_minutes: int = 60, 
                               duration_hours: int = 24) -> Dict[str, Any]:
        """Capture time-lapse sequence"""
        import asyncio
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sequence_dir = self.image_path / f"timelapse_{timestamp}"
        sequence_dir.mkdir(exist_ok=True)
        
        total_captures = int((duration_hours * 60) / interval_minutes)
        captured = 0
        
        self.logger.info(f"Starting time-lapse: {total_captures} images over {duration_hours}h")
        
        try:
            for i in range(total_captures):
                filename = f"frame_{i:04d}.jpg"
                filepath = sequence_dir / filename
                
                result = await self.capture_image(str(filepath))
                
                if "error" not in result:
                    captured += 1
                    self.logger.info(f"Time-lapse frame {i+1}/{total_captures} captured")
                else:
                    self.logger.error(f"Failed to capture frame {i+1}: {result['error']}")
                
                # Wait for next interval
                if i < total_captures - 1:
                    await asyncio.sleep(interval_minutes * 60)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "sequence_dir": str(sequence_dir),
                "total_frames": captured,
                "duration_hours": duration_hours,
                "interval_minutes": interval_minutes
            }
            
        except Exception as e:
            self.logger.error(f"Time-lapse capture failed: {e}")
            return {"error": str(e)}
    
    async def detect_growth_changes(self, reference_image_path: str, 
                                  current_image_path: str) -> Dict[str, Any]:
        """Compare two images to detect growth changes"""
        try:
            # Load images
            ref_img = cv2.imread(reference_image_path)
            curr_img = cv2.imread(current_image_path)
            
            if ref_img is None or curr_img is None:
                raise Exception("Failed to load comparison images")
            
            # Resize to same dimensions if needed
            if ref_img.shape != curr_img.shape:
                curr_img = cv2.resize(curr_img, (ref_img.shape[1], ref_img.shape[0]))
            
            # Convert to grayscale
            ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)
            
            # Calculate difference
            diff = cv2.absdiff(ref_gray, curr_gray)
            
            # Apply threshold to highlight changes
            _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            
            # Find contours (potential growth areas)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Analyze changes
            total_change_area = sum(cv2.contourArea(c) for c in contours)
            image_area = ref_img.shape[0] * ref_img.shape[1]
            change_percentage = (total_change_area / image_area) * 100
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "reference_image": reference_image_path,
                "current_image": current_image_path,
                "change_percentage": round(change_percentage, 2),
                "change_areas": len(contours),
                "significant_growth": change_percentage > 5.0
            }
            
        except Exception as e:
            self.logger.error(f"Growth detection failed: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """Clean up camera resources"""
        if self.cap and not self.mock:
            self.cap.release()
            self.logger.info("Camera resources cleaned up")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.cleanup()