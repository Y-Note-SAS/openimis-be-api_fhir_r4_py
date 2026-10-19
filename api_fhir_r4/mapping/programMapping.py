from api_fhir_r4.configurations import GeneralConfiguration, R4OrganisationConfig


class ProgramMapping:
    """
    CSU specific mapping of the ``program.Program`` model.

    A program is a funder (payer): it is exposed as an Organization of type ``pay``.
    Program has no UUID and its code is nullable and not unique, so the FHIR id is built
    from the technical id with a prefix. The prefix keeps the id apart from the numeric
    database ids that OrganisationViewSet resolves for health facilities.
    """

    ID_PREFIX = 'program-'
    ORGANIZATION_TYPE = 'pay'
    ORGANIZATION_TYPE_DISPLAY = 'Payer'
    # Program.code of the "Chèque Santé" program
    CHEQUE_SANTE_PROGRAM_CODE = 'CCS'

    @classmethod
    def to_fhir_id(cls, program):
        return f'{cls.ID_PREFIX}{program.idProgram}'

    @classmethod
    def from_fhir_id(cls, fhir_id):
        """Returns the Program.idProgram matching a FHIR id, None if it is not a program id."""
        fhir_id = str(fhir_id or '')
        if not fhir_id.startswith(cls.ID_PREFIX):
            return None
        raw_id = fhir_id[len(cls.ID_PREFIX):]
        return int(raw_id) if raw_id.isdigit() else None

    @classmethod
    def is_cheque_sante(cls, program):
        return program is not None and program.code == cls.CHEQUE_SANTE_PROGRAM_CODE

    @classmethod
    def organization_type_system(cls):
        return R4OrganisationConfig.get_fhir_ph_organisation_type_system()

    @classmethod
    def program_code_system(cls):
        return f'{GeneralConfiguration.get_system_base_url()}CodeSystem/program-code'

    @classmethod
    def cheque_sante_system(cls):
        return f'{GeneralConfiguration.get_system_base_url()}CodeSystem/cheque-sante'

    @classmethod
    def validity_extension_url(cls):
        return f'{GeneralConfiguration.get_system_base_url()}StructureDefinition/program-validity'

    @classmethod
    def cheque_status_extension_url(cls):
        return f'{GeneralConfiguration.get_system_base_url()}StructureDefinition/cheque-status'

    @classmethod
    def claim_program_extension_url(cls):
        return f'{GeneralConfiguration.get_system_base_url()}StructureDefinition/claim-program'
