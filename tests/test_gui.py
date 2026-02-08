import sys
import pytest
from PySide6.QtWidgets import QApplication
from src.animatic.main_window import AnimaticCreator

@pytest.fixture
def app(qtbot):
    test_app = QApplication.instance()
    if test_app is None:
        test_app = QApplication(sys.argv)
    return test_app

def test_window_creation(qtbot):
    """
    Verifies the window creation, title, and existence of key widgets.
    """
    window = AnimaticCreator()
    qtbot.addWidget(window)
    

    assert window.windowTitle() == "Pirates Animatic"
    
    assert window.acceptDrops() is True

    input_box = window.findChild(object, "InputBox")
    render_btn = window.findChild(object, "ActionBtn")

    assert input_box is not None, "Duration Input box is missing!"
    assert render_btn is not None, "Render Button is missing!"