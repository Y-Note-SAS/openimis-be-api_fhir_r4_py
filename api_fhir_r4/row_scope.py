"""Row scope for the FHIR resources whose module (pip `invoice` 1.7.0) does not
scope its own rows yet.

Invoice and Bill hang off a generic ``subject`` (a policy, a batch run...): they
are visible when their subject is, which is core's ``GenericScope``. Their
``get_queryset`` (invoice.mixins.GenericInvoiceQuerysetMixin) only blocks
anonymous users, so it is called first and the subject scope applied on top.

A payment notice is visible when every invoice/bill it settles is.

Move this into the invoice module (``row_scope = GenericScope("subject")``) once
Cameroon forks it; the views will keep working unchanged.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models import TextField
from django.db.models.functions import Cast

from core.models.row_security import GenericScope


def scoped_invoices(user):
    from invoice.models import Invoice
    queryset = Invoice.get_queryset(None, user)
    return GenericScope("subject").filter(queryset, user, Invoice)


def scoped_bills(user):
    from invoice.models import Bill
    queryset = Bill.get_queryset(None, user)
    return GenericScope("subject").filter(queryset, user, Bill)


def _pk_text(queryset):
    return queryset.annotate(_pk_text=Cast("pk", TextField())).values("_pk_text")


def scoped_payment_invoices(user):
    from invoice.models import Bill, DetailPaymentInvoice, Invoice, PaymentInvoice
    queryset = PaymentInvoice.get_queryset(None, user)
    if getattr(user, "is_superuser", False):
        return queryset
    details = DetailPaymentInvoice.objects.filter(is_deleted=False)
    invoice_ct = ContentType.objects.get_for_model(Invoice)
    bill_ct = ContentType.objects.get_for_model(Bill)
    foreign = (
        details.filter(subject_type=invoice_ct).exclude(subject_id__in=_pk_text(scoped_invoices(user)))
        | details.filter(subject_type=bill_ct).exclude(subject_id__in=_pk_text(scoped_bills(user)))
    )
    return queryset.exclude(id__in=foreign.values("payment_id"))
