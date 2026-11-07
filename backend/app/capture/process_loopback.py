"""只擷取指定程式（含子程式）播出的聲音：Windows 10 2004 起的 Process Loopback。"""
from __future__ import annotations

import ctypes
import threading
from ctypes import HRESULT, POINTER, byref, c_uint32, c_uint64, c_void_p, wintypes

import comtypes
from comtypes import COMMETHOD, GUID, IUnknown

VT_BLOB = 65
CLSCTX_ALL = 23
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD)]


class PROCESS_LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", ctypes.c_int)]


class AUDIOCLIENT_ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [("ActivationType", ctypes.c_int), ("ProcessLoopbackParams", PROCESS_LOOPBACK_PARAMS)]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("pBlobData", c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("blob", BLOB)]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(POINTER(ctypes.c_byte)), "data"),
                  (["out"], POINTER(c_uint32), "frames"), (["out"], POINTER(wintypes.DWORD), "flags"),
                  (["out"], POINTER(c_uint64), "position"), (["out"], POINTER(c_uint64), "qpc")),
        COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "frames")),
        COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint32), "frames")),
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Initialize", (["in"], ctypes.c_int, "mode"), (["in"], wintypes.DWORD, "flags"),
                  (["in"], ctypes.c_longlong, "duration"), (["in"], ctypes.c_longlong, "period"),
                  (["in"], POINTER(WAVEFORMATEX), "fmt"), (["in"], c_void_p, "session")),
        COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint32), "frames")),
        COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(ctypes.c_longlong), "latency")),
        COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(c_uint32), "padding")),
        COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], ctypes.c_int, "mode"), (["in"], POINTER(WAVEFORMATEX), "fmt"),
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "closest")),
        COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(POINTER(WAVEFORMATEX)), "fmt")),
        COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(ctypes.c_longlong), "default"),
                  (["out"], POINTER(ctypes.c_longlong), "minimum")),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle", (["in"], wintypes.HANDLE, "event")),
        COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "iid"), (["out"], POINTER(c_void_p), "service")),
    ]


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetActivateResult", (["out"], POINTER(HRESULT), "result"),
                  (["out"], POINTER(POINTER(IUnknown)), "interface")),
    ]


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = [
        COMMETHOD([], HRESULT, "ActivateCompleted", (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "operation")),
    ]


class IAgileObject(IUnknown):
    _iid_ = GUID("{94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90}")
    _methods_ = []


class _Handler(comtypes.COMObject):
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self):
        super().__init__()
        self.done = threading.Event()

    def ActivateCompleted(self, operation):
        self.done.set()
        return 0


_mmdevapi = ctypes.WinDLL("Mmdevapi.dll")
_activate = _mmdevapi.ActivateAudioInterfaceAsync
_activate.restype = HRESULT
_activate.argtypes = [wintypes.LPCWSTR, POINTER(GUID), POINTER(PROPVARIANT), c_void_p, POINTER(POINTER(IActivateAudioInterfaceAsyncOperation))]
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class ProcessLoopback:
    """以 16 kHz、單聲道、16 位元取得目標程式樹的聲音。"""

    def __init__(self, pid: int, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.fmt = WAVEFORMATEX(1, 1, sample_rate, sample_rate * 2, 2, 16, 0)
        params = AUDIOCLIENT_ACTIVATION_PARAMS(1, PROCESS_LOOPBACK_PARAMS(pid, 0))  # 0：包含子程式
        self._params = params
        prop = PROPVARIANT()
        prop.vt = VT_BLOB
        prop.blob = BLOB(ctypes.sizeof(params), ctypes.cast(ctypes.pointer(params), c_void_p))
        handler = _Handler()
        operation = POINTER(IActivateAudioInterfaceAsyncOperation)()
        handler_ptr = handler.QueryInterface(IActivateAudioInterfaceCompletionHandler)
        _activate("VAD\\Process_Loopback", byref(IAudioClient._iid_), byref(prop), handler_ptr, byref(operation))
        if not handler.done.wait(5):
            raise RuntimeError("process loopback activation timed out")
        result, unknown = operation.GetActivateResult()
        if result < 0:
            raise OSError(result, "process loopback activation failed")
        self.client = unknown.QueryInterface(IAudioClient)
        flags = (AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK |
                 AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY)
        self.client.Initialize(0, flags, 2_000_000, 0, byref(self.fmt), None)
        self.event = _kernel32.CreateEventW(None, False, False, None)
        self.client.SetEventHandle(self.event)
        service = self.client.GetService(byref(IAudioCaptureClient._iid_))
        self.capture = ctypes.cast(service, POINTER(IAudioCaptureClient))
        self.client.Start()

    def read(self, timeout_ms: int = 200) -> bytes:
        """回傳這段時間收到的 PCM；目標沒有聲音時 Windows 不會送資料，回傳空位元組。"""
        _kernel32.WaitForSingleObject(self.event, timeout_ms)
        out = bytearray()
        while True:
            size = self.capture.GetNextPacketSize()
            if not size:
                break
            data, frames, flags, _, _ = self.capture.GetBuffer()
            if frames:
                if flags & AUDCLNT_BUFFERFLAGS_SILENT:
                    out += bytes(frames * 2)
                else:
                    out += ctypes.string_at(data, frames * 2)
            self.capture.ReleaseBuffer(frames)
        return bytes(out)

    def close(self) -> None:
        try:
            self.client.Stop()
        finally:
            _kernel32.CloseHandle(self.event)
