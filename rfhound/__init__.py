"""RFHound - a friendly, powerful, receive-first HackRF reconnaissance & RF
situational-awareness toolkit.

RFHound is an *orchestration layer*. It does not re-implement DSP; instead it
drives best-of-breed command line tools (``hackrf_sweep``, ``hackrf_transfer``,
``rtl_433``, ``dump1090``, ``multimon-ng`` and friends) through one friendly,
guided interface, and it ships a frequency knowledge base so you know what you
are looking at.

Legal notice: transmitting is regulated everywhere. RFHound keeps transmit
functionality disabled by default and gated behind explicit authorization. See
``docs/LEGAL.md``.
"""

__version__ = "1.3.0"
__author__ = "RFHound contributors"

__all__ = ["__version__"]
