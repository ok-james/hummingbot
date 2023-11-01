class NotifierBase:
    def __init__(self):
        self._started = False

    # 广播消息
    def add_msg_to_queue(self, msg: str):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError
