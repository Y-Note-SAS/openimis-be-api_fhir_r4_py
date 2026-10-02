import datetime

from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from api_fhir_r4.permissions import FHIRApiCoverageRequestPermissions
from api_fhir_r4.serializers.coverageSerializer import CoverageSerializer
from api_fhir_r4.views.fhir.base import BaseFHIRView
from api_fhir_r4.views.filters import ValidityFromRequestParameterFilter
from policy.models import Policy


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

        Preloads the Cheque Santé registry statuses for the serialized policies so the
        Coverage converter does not issue one query per coverage.
        """
        cheque_numbers = [
            policy.policy_number
            for policy in policies or []
            if getattr(policy, "policy_number", None)
        ]
        if not cheque_numbers:
            return
        try:
            from cs.models import ChequeImportLine
        except ImportError:
            return
        statuses = dict(
            ChequeImportLine.objects.filter(chequeImportLineCode__in=cheque_numbers)
            .values_list("chequeImportLineCode", "chequeImportLineStatus")
        )
        for policy in policies:
            policy.csu_cheque_status = statuses.get(policy.policy_number)

    def get_queryset(self):
        queryset = Policy.get_queryset(None, self.request.user)
        return ValidityFromRequestParameterFilter(self.request).filter_queryset(queryset)
