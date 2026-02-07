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
    Verifies that the main window can be instantiated 
    and has the correct title.
    """
    window = AnimaticCreator()
    qtbot.addWidget(window)
    
    assert window.windowTitle() == "Animatic Creator"
    assert window.acceptDrops() is True