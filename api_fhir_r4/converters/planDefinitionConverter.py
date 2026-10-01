from fhir.resources.R4B.plandefinition import PlanDefinition
from fhir.resources.R4B.period import Period

from api_fhir_r4.configurations import GeneralConfiguration, R4IdentifierConfig
from api_fhir_r4.converters import BaseFHIRConverter, ReferenceConverterMixin


class PlanDefinitionConverter(BaseFHIRConverter, ReferenceConverterMixin):
    """
    CSU specific converter.

    Exposes the openIMIS CSU ``program.Program`` concept as a FHIR R4
    ``PlanDefinition``. The resource is read-only: the program catalogue is
    maintained in openIMIS and consumed by external systems through OpenHIM.
    """

    @classmethod
    def to_fhir_obj(cls, imis_program, reference_type=ReferenceConverterMixin.UUID_REFERENCE_TYPE):
        fhir_plan_definition = PlanDefinition.construct(status="active")
        cls.build_fhir_pk(fhir_plan_definition, imis_program)
        cls.build_fhir_identifiers(fhir_plan_definition, imis_program)
        cls.build_fhir_name(fhir_plan_definition, imis_program)
        cls.build_fhir_effective_period(fhir_plan_definition, imis_program)
        return fhir_plan_definition

    @classmethod
    def to_imis_obj(cls, data, audit_user_id):
        raise NotImplementedError('PlanDefinition is a read-only resource in openIMIS CSU.')

    @classmethod
    def get_fhir_resource_type(cls):
        return PlanDefinition

    @classmethod
    def get_reference_obj_id(cls, imis_program):
        return imis_program.idProgram

    @classmethod
    def get_reference_obj_uuid(cls, imis_program):
        # Program has no uuid, its technical id is used instead.
        return imis_program.idProgram

    @classmethod
    def get_reference_obj_code(cls, imis_program):
        return imis_program.code

    @classmethod
    def build_fhir_pk(cls, fhir_obj, resource, reference_type: str = None):
        cls._build_simple_pk(fhir_obj, resource.idProgram)

    @classmethod
    def build_fhir_identifiers(cls, fhir_obj, imis_program):
        identifiers = [
            cls.build_fhir_identifier(
                imis_program.idProgram,
                R4IdentifierConfig.get_fhir_identifier_type_system(),
                R4IdentifierConfig.get_fhir_id_type_code(),
            )
        ]
        if imis_program.code:
            identifiers.append(
                cls.build_fhir_identifier(
                    imis_program.code,
                    f'{GeneralConfiguration.get_system_base_url()}/CodeSystem/program',
                    'program-code',
                )
            )
        fhir_obj.identifier = identifiers

    @classmethod
    def build_fhir_name(cls, fhir_obj, imis_program):
        fhir_obj.name = imis_program.nameProgram
        fhir_obj.title = imis_program.nameProgram

    @classmethod
    def build_fhir_effective_period(cls, fhir_obj, imis_program):
        period = Period.construct()
        if imis_program.validityDateFrom:
            period.start = imis_program.validityDateFrom.date().isoformat()
        if imis_program.validityDateTo:
            period.end = imis_program.validityDateTo.date().isoformat()
        fhir_obj.effectivePeriod = period
