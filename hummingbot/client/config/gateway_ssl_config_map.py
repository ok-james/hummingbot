from pydantic import Field

from hummingbot.client.config.config_data_types import BaseClientModel


class SSLConfigMap(BaseClientModel):
    # ca 证书文件
    caCertificatePath: str = Field(default="/usr/src/app/certs/ca_cert.pem")
    # 公钥证书文件，它包含服务器的公钥以及其他相关信息，客户端可以使用它来验证服务器的身份
    certificatePath: str = Field(default="/usr/src/app/certs/server_cert.pem")
    # 私钥文件
    keyPath: str = Field(default="/usr/src/app/certs/server_key.pem")
