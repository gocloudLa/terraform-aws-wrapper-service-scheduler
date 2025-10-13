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
| <a href="https://github.com/terraform-aws-modules/terraform-aws-eventbridge" target="_blank">terraform-aws-modules/eventbridge/aws</a> | 4.2.1 |
| <a href="https://github.com/terraform-aws-modules/terraform-aws-lambda" target="_blank">terraform-aws-modules/lambda/aws</a> | 8.1.0 |



## 🚀 Quick Start
```hcl
service_scheduler_parameters = {
    enable = true # Default: false

    power_on_schedule  = "cron(0 11 * * ? *)" # 8AM UTC-3 / null or commented to disable
    power_off_schedule = "cron(0 23 * * ? *)" # 8PM UTC-3 / null or commented to disable

  }
```


## 🔧 Additional Features Usage



## 📑 Inputs
| Name                              | Description                                                                            | Type     | Default     | Required |
| --------------------------------- | -------------------------------------------------------------------------------------- | -------- | ----------- | -------- |
| enable                            | Controls creation of services                                                          | `bool`   | `"true"`    | no       |
| power_on_schedule                 | Controls CRON expression for startup                                                   | `string` | `null`      | no       |
| power_off_schedule                | Controls CRON expression for shutdown                                                  | `string` | `null`      | no       |
| default_selection_mode            | Controls service selection mode                                                        | `string` | `"include"` | no       |
| enable_scheduler_ecs              | Controls inclusion of ECS service in automation                                        | `bool`   | `true`      | no       |
| enable_scheduler_rds              | Controls inclusion of RDS service in automation                                        | `bool`   | `true`      | no       |
| enable_scheduler_ec2              | Controls inclusion of EC2 service in automation                                        | `bool`   | `true`      | no       |
| enable_scheduler_asg              | Controls inclusion of ASG service in automation                                        | `bool`   | `true`      | no       |
| cloudwatch_logs_retention_in_days | CloudWatch log retention in days                                                       | `number` | `14`        | no       |
| log_level                         | Logging level configuration                                                            | `string` | `"INFO"`    | no       |
| ipv6_allowed_for_dual_stack       | Allows outbound IPv6 traffic on VPC functions that are connected to dual-stack subnets | `bool`   | `null`      | no       |
| recursive_loop                    | Lambda function recursion configuration. Valid values are Allow or Terminate.          | `string` | `null`      | no       |
| include_default_tag               | include_default_tag                                                                    | `bool`   | `true`      | no       |
| tags                              | A map of tags to assign to resources.                                                  | `map`    | `{}`        | no       |







## ⚠️ Important Notes
### Operation Details
#### Resources
The infrastructure includes the following resources:
* Main lambda function
* DynamoDB table
* Event Bridge Rule (power-off) (optional)
* Event Bridge Rule (power-on) (optional)

#### Workflow
Operation Workflow:
* **START**<br/>
The lambda starts with the parameters and verifies if it can execute.<br/>
(the same action cannot be executed twice in a row)
  * The requested action is persisted in DynamoDB with status (begin).
* **PROCESS**
  * If **power-off** action is executed:
    * The lambda function performs discovery of services to manage.
    * Persists the current state (prior to power-off) in DynamoDB.
    * Updates the configuration to turn off the services.
  * If **power-on** action is executed:
    * The lambda function discovers the last state of services saved in DynamoDB.
    * Updates the service configuration to match the saved state.
* **END**<br/>
The function completes successfully:
  * The requested action is persisted in DynamoDB with status (end).

---

### Configuration Modes (include / exclude)
**Include Mode** (Default)<br/>
Variable: `default_selection_mode = "include"`<br/>
Causes **ALL** services to be included within the application logic for automatic shutdown and startup scheduling, except for services that have the tag `AutomaticScheduler: false`<br/>

**Exclude Mode**<br/>
Variable: `default_selection_mode = "exclude"`<br/>
Causes **ALL** services to be excluded from the application logic for automatic shutdown and startup scheduling, except for services that have the tag `AutomaticScheduler: true`<br/>



---

## 🤝 Contributing
We welcome contributions! Please see our contributing guidelines for more details.

## 🆘 Support
- 📧 **Email**: info@gocloud.la

## 🧑‍💻 About
We are focused on Cloud Engineering, DevOps, and Infrastructure as Code.
We specialize in helping companies design, implement, and operate secure and scalable cloud-native platforms.
- 🌎 [www.gocloud.la](https://www.gocloud.la)
- ☁️ AWS Advanced Partner (Terraform, DevOps, GenAI)
- 📫 Contact: info@gocloud.la

## 📄 License
This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details. 