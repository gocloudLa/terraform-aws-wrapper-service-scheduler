/*----------------------------------------------------------------------*/
/* Common |                                                             */
/*----------------------------------------------------------------------*/

variable "metadata" {
  type = any
}

/*----------------------------------------------------------------------*/
/* Services Scheduler | Variable Definition                             */
/*----------------------------------------------------------------------*/
variable "service_scheduler_parameters" {
  type        = any
  description = "Service Scheduler parameteres"
  default     = {}
}

variable "service_scheduler_defaults" {
  type        = any
  description = "Service Scheduler default parameteres"
  default     = {}
}