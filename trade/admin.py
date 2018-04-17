from time import strftime

from django.conf import settings
from ikwen_kakocase.trade.models import Order
from import_export import resources, fields


class OrderResource(resources.ModelResource):
    created_on = fields.Field(column_name='Date')
    rcc = fields.Field(column_name='RCC')
    client = fields.Field(column_name='Client')
    shipping_cost = fields.Field(column_name='Shipping Cost')
    if not getattr(settings, 'IS_PROVIDER', False):
        provider = fields.Field(column_name='Merchant')
    if getattr(settings, 'IS_PROVIDER', False):
        payment_mean = fields.Field(column_name='Payment Method')
        delivery_company = fields.Field(column_name='DelCom')
    if not getattr(settings, 'IS_DELIVERY_COMPANY', False):
        items_cost = fields.Field(column_name='Items Cost')
        deal = fields.Field(column_name='Deal')
    if not getattr(settings, 'IS_BANK', False):
        details = fields.Field(column_name='Details')
        delivery_address = fields.Field(column_name='Address')
        delivery_option = fields.Field(column_name='Del. Option')
    if getattr(settings, 'IS_BANK', False):
        account_number = fields.Field(column_name='Account Number')

    class Meta:
        model = Order
        if getattr(settings, 'IS_PROVIDER', False):
            fields = ('created_on', 'rcc', 'client', 'details', 'delivery_address', 'delivery_option',
                      'delivery_company', 'items_cost', 'shipping_cost', 'payment_mean', 'deal')
            export_order = ('client', 'rcc', 'created_on', 'details', 'delivery_address', 'delivery_option',
                            'delivery_company', 'items_cost', 'shipping_cost', 'payment_mean', 'deal', )
        elif getattr(settings, 'IS_DELIVERY_COMPANY', False):
            fields = ('created_on', 'rcc', 'client', 'details',
                      'delivery_address', 'delivery_option', 'shipping_cost', 'provider', )
            export_order = ('client', 'rcc', 'created_on', 'details',
                            'delivery_address', 'delivery_option', 'shipping_cost', 'provider', )
        elif getattr(settings, 'IS_BANK', False):
            fields = ('created_on', 'rcc', 'client', 'account_number', 'items_cost', 'shipping_cost', 'deal', 'provider')
            export_order = ('client', 'account_number', 'rcc', 'created_on', 'items_cost', 'shipping_cost', 'deal', 'provider', )

    def dehydrate_created_on(self, order):
        return order.created_on.strftime('%y-%m-%d %H:%M')

    def dehydrate_rcc(self, order):
        return order.rcc.upper()

    def dehydrate_client(self, order):
        member = order.member
        if member:
            return member.full_name
        return order.anonymous_buyer.name

    def dehydrate_account_number(self, order):
        return order.account_number

    def dehydrate_details(self, order):
        details = []
        for entry in order.entries:
            product = entry.product
            detail = product.name
            if product.reference:
                detail += ' - Ref: %s' % product.reference
            if product.size:
                detail += ' - Size: %s' % product.size
            detail = '%s - Qty: %d' % (detail, entry.count)
            details.append(detail)
        return '\n'.join(details)

    def dehydrate_delivery_address(self, order):
        a = order.delivery_address
        address = 'Name: %s\n%s' % (a.name, a.details)
        if a.postal_code:
            address += ' - %s' % a.postal_code
        if a.country:
            address += '\n%s - %s' % (a.city, a.country.iso3.upper())
        address += '\n%s' % a.phone
        if a.email:
            address += '\n%s' % a.email
        return address

    def dehydrate_deal(self, order):
        d = order.deal
        if d is None:
            return 'N/A'
        if d.product_slug is None:
            return 'Cash'
        deal = '%d/%s - %d %ss - First term: %d' % (d.term_cost, d.frequency, d.terms_count, d.frequency, d.first_term)
        return deal

    def dehydrate_payment_mean(self, order):
        p = order.payment_mean
        if p is None:
            return 'MTN MoMo'
        return p.name

    def dehydrate_items_cost(self, order):
        return order.items_cost

    def dehydrate_shipping_cost(self, order):
        return order.delivery_option.cost

    def dehydrate_delivery_company(self, order):
        return order.delivery_company.config.company_name

    def dehydrate_delivery_option(self, order):
        return order.delivery_option.name

    def dehydrate_provider(self, order):
        return order.retailer.config.company_name
