import datetime

from django.core.exceptions import FieldDoesNotExist
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from api_fhir_r4.permissions import FHIRApiCoverageRequestPermissions
from api_fhir_r4.serializers.coverageSerializer import CoverageSerializer
from api_fhir_r4.views.fhir.base import BaseFHIRView
from api_fhir_r4.mapping.programMapping import ProgramMapping
from api_fhir_r4.views.filters import ValidityFromRequestParameterFilter
from policy.models import Policy
from product.models import Product


class CoverageRequestQuerySet(BaseFHIRView, mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.UpdateModelMixin,
                              mixins.CreateModelMixin, GenericViewSet):
    lookup_field = 'uuid'
    serializer_class = CoverageSerializer
    permission_classes = (FHIRApiCoverageRequestPermissions,)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        queryset.prefetch_related('services')
        refDate = request.GET.get('refDate')
        refEndDate = request.GET.get('refEndDate')
        identifier = request.GET.get("identifier")
        if identifier:
            queryset = queryset.filter(chf_id=identifier)
        else:
            queryset = queryset.filter(validity_to__isnull=True).order_by('validity_from')
            if refDate != None:
                isValidDate = True
                try:
                    datevar = datetime.datetime.strptime(refDate, "%Y-%m-%d").date()
                except ValueError:
                    isValidDate = False
                queryset = queryset.filter(validity_from__gte=datevar)
            if refEndDate != None:
                isValidDate = True
                try:
                    datevar = datetime.datetime.strptime(refEndDate, "%Y-%m-%d").date()
                except ValueError:
                    isValidDate = False
                queryset = queryset.filter(validity_from__lt=datevar)

        page = self.paginate_queryset(queryset)
        self.prefetch_csu_cheque_status(page)
        serializer = CoverageSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @staticmethod
    def prefetch_csu_cheque_status(policies):
        """
        CSU specific.

        Preloads the cheque registry statuses of the serialized "Chèque Santé" policies so the Coverage
        converter does not issue one query per coverage.
        """
        policies = [
            policy for policy in policies or []
            if getattr(policy, 'policy_number', None)
            and ProgramMapping.is_cheque_sante(getattr(policy.product, 'program', None))
        ]
        if not policies:
            return
        # Imported lazily: the cheque registry is only installed on CSU instances.
        try:
            from cs.models import ChequeImportLine
        except ImportError:
            return
        # Ordered by id so that, as in the converter fallback, the latest registry entry wins.
        statuses = dict(
            ChequeImportLine.objects
            .filter(chequeImportLineCode__in=[policy.policy_number for policy in policies])
            .order_by('idChequeImportLine')
            .values_list('chequeImportLineCode', 'chequeImportLineStatus')
        )
        for policy in policies:
            policy.csu_cheque_status = statuses.get(policy.policy_number)

    @staticmethod
    def _select_product_program(queryset):
        # Product.program only exists with the program module: preload it to avoid one query per coverage.
        try:
            Product._meta.get_field('program')
        except FieldDoesNotExist:
            return queryset
        return queryset.select_related('product__program')

    def get_queryset(self):
        queryset = self._select_product_program(Policy.get_queryset(None, self.request.user))
        return ValidityFromRequestParameterFilter(self.request).filter_queryset(queryset)
