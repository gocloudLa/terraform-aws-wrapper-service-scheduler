# Standard Platform - Terraform Module 🚀🚀
<p align="right"><a href="https://partners.amazonaws.com/partners/0018a00001hHve4AAC/GoCloud"><img src="https://img.shields.io/badge/AWS%20Partner-Advanced-orange?style=for-the-badge&logo=amazonaws&logoColor=white" alt="AWS Partner"/></a><a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green?style=for-the-badge&logo=apache&logoColor=white" alt="LICENSE"/></a></p>

Welcome to the Standard Platform — a suite of reusable and production-ready Terraform modules purpose-built for AWS environments.
Each module encapsulates best practices, security configurations, and sensible defaults to simplify and standardize infrastructure provisioning across projects.

## 📦 Module: Terraform ECS Scheduler Module
<p align="right"><a href="https://github.com/gocloudLa/terraform-aws-wrapper-service-scheduler/releases/latest"><img src="https://img.shields.io/github/v/release/gocloudLa/terraform-aws-wrapper-service-scheduler.svg?style=for-the-badge" alt="Latest Release"/></a><a href=""><img src="https://img.shields.io/github/last-commit/gocloudLa/terraform-aws-wrapper-service-scheduler.svg?style=for-the-badge" alt="Last Commit"/></a><a href="https://registry.terraform.io/modules/gocloudLa/wrapper-service-scheduler/aws"><img src="https://img.shields.io/badge/Terraform-Registry-7B42BC?style=for-the-badge&logo=terraform&logoColor=white" alt="Terraform Registry"/></a></p>
The Terraform Wrapper for Service Scheduler provides the implementation of a lambda function and two event bridge events to handle the scheduled shutdown and startup of various services, an idea for shutting down environments during non-productive hours.

### ✨ Features



### 🔗 External Modules
| Name | Version |
|------|------:|
| [terraform-aws-modules/eventbridge/aws](https://github.com/terraform-aws-modules/eventbridge-aws) | 4.1.0 |
| [terraform-aws-modules/lambda/aws](https://github.com/terraform-aws-modules/lambda-aws) | 8.0.1 |



## 🚀 Quick Start
```hcl
service_scheduler_parameters = {
    enable = true # Default: false

    power_on_schedule  = "cron(0 11 * * ? *)" # 8AM UTC-3 / null or commented to disable
    power_off_schedule = "cron(0 23 * * ? *)" # 8PM UTC-3 / null or commented to disable

    # default_selection_mode = "include"
    # enable_scheduler_ecs   = true   # Default: true
    # enable_scheduler_rds   = true   # Default: true
    # enable_scheduler_ec2   = true   # Default: true
    # cloudwatch_logs_retention_in_days = 14
    # log_level = "INFO"
  }
```


## 🔧 Additional Features Usage









## ⚠️ Important Notes
### Detalles de funcionamiento
#### Recursos
La infraestructura cuenta con los siguientes recursos
* Funcion lambda principal
* Tabla de DynamoDB
* Event Bridge Rule (power-off) (opcional)
* Event Bridge Rule (power-on) (opcional)

#### WorkFlow
Workflow de Funcionamiento
* **INICIO**<br/>
Inicia la lambda con los parametros y verifica si puede ejecutar.<br/>
(no se puede ejecutar dos veces seguidas la misma accion)
  * Se persiste en DynamoDB la accion solicitada con status (begin).
* **PROCESO**
  * Si se ejecuta accion **power-off**
    * La funcion lambda hace un discovery de los servicios a manejar.
    * Persiste el estado actual (previo al power-off) en DynamoDB.
    * Actualiza la configuracion para que se apaguen los servicios.
  * Si se ejecuta accion **power-on**
    * La funcion lambda hace un discovery del ultimo estado de los servicios guardados en DynamoDB.
    * Actualiza la configuracion de los servicios para hacer match con el estado guardado.
* **FIN**<br/>
Finaliza la fucion en forma exitosa
  * Se persiste en DynamoDB la accion solicitada con status (end).

---

### Modos de Configuracion (include / exclude)
**Modo Include** (Default)<br/>
Variable: `default_selection_mode = "include"`<br/>
Provoca que se incluyan **TODOS** los servicios dentro de la logica del aplicativo para su programacion de apagado y encendido automatico a exepcion de los servicios que cuenten con el tag `AutomaticScheduler: false`<br/>

**Modo Exclude**<br/>
Variable: `default_selection_mode = "exclude"`<br/>
Provoca que se excluyan **TODOS** los servicios dentro de la logica del aplicativo para su programacion de apagado y encendido automatico a exepcion de los servicios que cuenten con el tag `AutomaticScheduler: true`<br/>



---

## 🤝 Contributing
We welcome contributions! Please see our contributing guidelines for more details.

## 🆘 Support
- 📧 **Email**: info@gocloud.la
- 🐛 **Issues**: [GitHub Issues](https://github.com/gocloudLa/issues)

## 🧑‍💻 About
We are focused on Cloud Engineering, DevOps, and Infrastructure as Code.
We specialize in helping companies design, implement, and operate secure and scalable cloud-native platforms.
- 🌎 [www.gocloud.la](https://www.gocloud.la)
- ☁️ AWS Advanced Partner (Terraform, DevOps, GenAI)
- 📫 Contact: info@gocloud.la

## 📄 License
This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details. 