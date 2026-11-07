"""OPC 模版命令的公共异常。"""


class OpcError(Exception):
    """可预期的用户错误：打印消息并以非零码退出，不打印 traceback。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.message = message
        self.code = code
