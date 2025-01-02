import pytest
from baresip import BareSIP

def test_start():
    bs = BareSIP()
    assert bs._process == None
    assert bs._thread == None
    bs.start()
    assert bs._process != None
    assert bs._thread != None
    
def test_stop():
    bs = BareSIP()
    assert bs._process == None
    assert bs._thread == None
    bs.start()
    assert bs._process != None
    assert bs._thread != None
    bs.stop()
    assert bs._process == None
    assert bs._thread == None
    assert bs._is_running == False

def test_start_stop():
    bs = BareSIP()
    assert bs._process == None
    assert bs._thread == None
    bs.start()
    assert bs._process != None
    assert bs._thread != None
    bs.stop()
    assert bs._process == None
    assert bs._thread == None
    bs.start()
    assert bs._process != None
    assert bs._thread != None

def test_get_user_agents():
    
    bs = BareSIP()
    assert bs._process == None
    assert bs._thread == None
    bs.start()
    assert bs._process != None
    assert bs._thread != None
    
    bs.create_user_agent("user", "password", "domain")
    a = bs.user_agents()

    assert len(a) == 1
    assert a[0].user == "user"
    assert a[0].domain == "domain"
    assert a[0].registered == False