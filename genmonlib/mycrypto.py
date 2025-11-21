#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mycrypto.py
# PURPOSE: AES Encryption using python cryptography module
#
#  AUTHOR: Jason G Yates
#    DATE: 08-23-2020
#
# MODIFICATIONS:
#
# USAGE:
#
# -------------------------------------------------------------------------------

"""
Module for AES Encryption/Decryption.

This module provides the `MyCrypto` class which wraps the `cryptography`
library to perform AES-128 CBC encryption and decryption.
"""

import sys
from typing import Optional, Union, Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from genmonlib.mycommon import MyCommon


# ------------ MyCrypto class -------------------------------------------------
class MyCrypto(MyCommon):
    """
    A class for AES encryption and decryption operations.

    Attributes:
        log (Any): Logger instance.
        console (Any): Console logger instance.
        key (bytes): Encryption key (16 bytes for AES-128).
        iv (bytes): Initialization vector (16 bytes).
        keysize (int): Key size in bytes.
        blocksize (int): Block size in bytes.
        debug (bool): Debug mode flag.
        backend (Any): Cryptography backend.
        cipher (Cipher): Cipher instance.
        decryptor (Any): Decryptor context.
        encryptor (Any): Encryptor context.
    """

    def __init__(
        self,
        log: Any = None,
        console: Any = None,
        key: Optional[bytes] = None,
        iv: Optional[bytes] = None,
    ):
        """
        Initializes the MyCrypto instance.

        Args:
            log (Any, optional): Logger instance. Defaults to None.
            console (Any, optional): Console logger instance. Defaults to None.
            key (bytes, optional): AES key. Defaults to None.
            iv (bytes, optional): Initialization vector. Defaults to None.
        """
        self.log = log
        self.console = console
        self.key = key  # bytes
        self.iv = iv  # bytes
        self.keysize = len(key) if key else 0 # in bytes
        self.blocksize = len(key) if key else 0 # in bytes

        self.debug = False
        # presently only AES-128 CBC mode is supported
        if self.keysize != 16:
            self.LogError("MyCrypto: WARNING: key size not 128: " + str(self.keysize))

        if iv and len(self.iv) != 16:
            self.LogError("MyCrypto: WARNING: iv size not 128: " + str(len(self.iv)))
        try:
            self.backend = default_backend()
            self.cipher = Cipher(
                algorithms.AES(self.key), modes.CBC(self.iv), backend=self.backend
            )
            self.decryptor = self.cipher.decryptor()
            self.encryptor = self.cipher.encryptor()

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:init: " + str(e1))
            sys.exit(1)

    def Encrypt(self, cleartext: bytes, finalize: bool = True) -> Optional[bytes]:
        """
        Encrypts a single block of data.

        Args:
            cleartext (bytes): Data to encrypt (must match keysize).
            finalize (bool, optional): Whether to finalize the encryption.
                Defaults to True.

        Returns:
            Optional[bytes]: Encrypted data or None on error.
        """
        try:
            if len(cleartext) != self.keysize:
                self.LogError(
                    "MyCrypto:Encrypt: Blocksize mismatch: %d, %d"
                    % (len(cleartext), self.keysize)
                )
                return None
            if finalize:
                retval = self.encryptor.update(cleartext) + self.encryptor.finalize()
                self.Restart()
                return retval
            else:
                return self.encryptor.update(cleartext)
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Encrypt: " + str(e1))
            return None

    def Decrypt(self, cyptertext: bytes, finalize: bool = True) -> Optional[bytes]:
        """
        Decrypts a single block of data.

        Args:
            cyptertext (bytes): Data to decrypt (must match keysize).
            finalize (bool, optional): Whether to finalize the decryption.
                Defaults to True.

        Returns:
            Optional[bytes]: Decrypted data or None on error.
        """
        try:
            if len(cyptertext) != self.keysize:
                self.LogError(
                    "MyCrypto:Decrypt: Blocksize mismatch: %d, %d"
                    % (len(cyptertext), self.keysize)
                )
                return None

            if finalize:
                retval = self.decryptor.update(cyptertext) + self.decryptor.finalize()
                self.Restart()
                return retval
            else:
                return self.decryptor.update(cyptertext)
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Decrypt: " + str(e1))
            return None

    def Restart(self, key: Optional[bytes] = None, iv: Optional[bytes] = None) -> None:
        """
        Resets the encryption/decryption context with new or existing keys.

        Args:
            key (bytes, optional): New key. Defaults to None (keep existing).
            iv (bytes, optional): New IV. Defaults to None (keep existing).
        """
        try:
            if key is not None:
                self.key = key
            if iv is not None:
                self.iv = iv
            self.cipher = Cipher(
                algorithms.AES(self.key), modes.CBC(self.iv), backend=self.backend
            )
            self.decryptor = self.cipher.decryptor()
            self.encryptor = self.cipher.encryptor()
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Restart: " + str(e1))
            return None

    def EncryptBuff(
        self, plaintext_buff: bytes, pad_zero: bool = True
    ) -> Optional[bytes]:
        """
        Encrypts a buffer of data (multiple blocks).

        Args:
            plaintext_buff (bytes): Data to encrypt.
            pad_zero (bool, optional): Whether to pad the last block with zeros.
                Defaults to True.

        Returns:
            Optional[bytes]: Encrypted buffer or None on error.
        """
        try:
            if plaintext_buff is None:
                self.LogError("MyCrypto:EncryptBuff: Error: invalid buffer! ")
                return None
            if len(plaintext_buff) == 0:
                self.LogError(
                    "MyCrypto:EncryptBuff: Warning: plaintext buffer size is invalid"
                )
                return None

            if len(plaintext_buff) % self.blocksize:
                self.LogDebug(
                    "MyCrypto:EncryptBuff: WARNING: buffer is not a multipe of blocksize"
                )
            index1 = 0
            index2 = self.blocksize
            ct_buf = b""
            while True:
                if index2 > len(plaintext_buff):
                    # remaining bytes are not block size
                    buff = plaintext_buff[index1:]
                    if pad_zero:
                        for i in range(0, (self.blocksize - len(buff))):
                            buff += b"\0"
                        encrypted_chunk = self.Encrypt(buff)
                        if encrypted_chunk:
                            ct_buf += encrypted_chunk
                        break
                    else:
                        # append plain text to cryptotext buffer
                        ct_buf += buff
                    break
                buff = plaintext_buff[index1:index2]
                encrypted_chunk = self.Encrypt(buff)
                if encrypted_chunk:
                    ct_buf += encrypted_chunk

                index1 += self.blocksize
                index2 += self.blocksize
                if index1 == len(plaintext_buff):
                    break
            return ct_buf

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:EncryptBuff: " + str(e1))
            return None

    def DecryptBuff(
        self, crypttext_buff: bytes, pad_zero: bool = True
    ) -> Optional[bytes]:
        """
        Decrypts a buffer of data (multiple blocks).

        Args:
            crypttext_buff (bytes): Data to decrypt.
            pad_zero (bool, optional): Whether to pad/handle last block.
                Defaults to True.

        Returns:
            Optional[bytes]: Decrypted buffer or None on error.
        """
        try:
            if crypttext_buff is None:
                self.LogError("MyCrypto:DecryptBuff: Error: invalid buffer! ")
                return None
            if len(crypttext_buff) < self.blocksize:
                self.LogError(
                    "MyCrypto:DecryptBuff: Error: crypttext buffer size less than blocksize"
                )
                return None

            if len(crypttext_buff) % self.blocksize:
                self.LogDebug(
                    "MyCrypto:DecryptBuff: WARNING: buffer is not a multipe of blocksize"
                )

            index1 = 0
            index2 = self.blocksize
            pt_buf = b""
            while True:
                if index2 > len(crypttext_buff):
                    # remaining bytes are not block size
                    buff = crypttext_buff[index1:]
                    if pad_zero:
                        for i in range(0, (self.blocksize - len(buff))):
                            buff += b"\0"
                        decrypted_chunk = self.Decrypt(buff)
                        if decrypted_chunk:
                            pt_buf += decrypted_chunk
                        break
                    else:
                        # append plain text to cryptotext buffer
                        pt_buf += buff
                    break
                buff = crypttext_buff[index1:index2]
                decrypted_chunk = self.Decrypt(buff)
                if decrypted_chunk:
                    pt_buf += decrypted_chunk
                index1 += self.blocksize
                index2 += self.blocksize
                if index1 == len(crypttext_buff):
                    break

            return pt_buf

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:EncryptBuff: " + str(e1))
            return None
