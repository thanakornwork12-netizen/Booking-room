import smtplib
import socket

from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend


class IPv4SMTP(smtplib.SMTP):
    """smtplib.SMTP ที่บังคับต่อผ่าน IPv4 เท่านั้น"""

    def _get_socket(self, host, port, timeout):
        family, socktype, proto, _canonname, sockaddr = socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_STREAM
        )[0]
        sock = socket.socket(family, socktype, proto)
        if timeout is not None:
            sock.settimeout(timeout)
        sock.connect(sockaddr)
        return sock


class EmailBackend(DjangoSMTPBackend):
    """
    Container บน Render resolve smtp.gmail.com ได้ทั้ง IPv4/IPv6 แต่ไม่มี
    เส้นทาง IPv6 ออกจริง — smtplib เลือกต่อ IPv6 ก่อนตามลำดับที่ getaddrinfo
    คืนมา แล้วเจอ OSError: Network is unreachable (errno 101) ทุกครั้ง
    ต่อให้ credential ถูกก็ไม่มีทางส่งผ่าน จึงบังคับให้ต่อผ่าน IPv4 เสมอ
    """

    def open(self):
        if self.connection:
            return False
        try:
            self.connection = IPv4SMTP(
                self.host, self.port,
                local_hostname='localhost',
                timeout=self.timeout,
            )
            self.connection.ehlo()
            if self.use_tls:
                self.connection.starttls()
                self.connection.ehlo()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise
            return None
