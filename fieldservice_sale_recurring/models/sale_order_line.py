# Copyright (C) 2019 Brian McMaster
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    fsm_recurring_id = fields.Many2one(
        "fsm.recurring",
        "Recurring Order",
        index=True,
        help="Field Service Recurring Order generated by the sale order line",
    )

    def _field_create_fsm_recurring_prepare_values(self):
        self.ensure_one()
        template = self.product_id.fsm_recurring_template_id
        product = self.product_id
        note = self.name
        if template.description:
            note += "\n " + template.description
        return {
            "location_id": self.order_id.fsm_location_id.id,
            "start_date": self.order_id.expected_date,
            "fsm_recurring_template_id": template.id,
            "description": note,
            "max_orders": template.max_orders,
            "fsm_frequency_set_id": template.fsm_frequency_set_id.id,
            "fsm_order_template_id": product.fsm_order_template_id.id
            or template.fsm_order_template_id.id,
            "sale_line_id": self.id,
            "company_id": self.company_id.id,
        }

    def _field_create_fsm_recurring(self):
        """Generate fsm_recurring for the given so line, and link it.
        :return a mapping with the so line id and its linked fsm_recurring
        :rtype dict
        """
        result = {}
        for so_line in self:
            # create fsm_recurring
            values = so_line._field_create_fsm_recurring_prepare_values()
            fsm_recurring = self.env["fsm.recurring"].sudo().create(values)
            so_line.write({"fsm_recurring_id": fsm_recurring.id})
            # post message on SO
            msg_body = (
                _(
                    """Field Service recurring Created (%s): <a href=
                   # data-oe-model=fsm.recurring data-oe-id=%d>%s</a>
                """
                )
                % (so_line.product_id.name, fsm_recurring.id, fsm_recurring.name)
            )
            so_line.order_id.message_post(body=msg_body)
            # post message on fsm_recurring
            fsm_recurring_msg = (
                _(
                    """This recurring has been created from: <a href=
                   # data-oe-model=sale.order data-oe-id=%d>%s</a> (%s)
                """
                )
                % (so_line.order_id.id, so_line.order_id.name, so_line.product_id.name)
            )
            fsm_recurring.message_post(body=fsm_recurring_msg)
            result[so_line.id] = fsm_recurring
        return result

    def _field_find_fsm_recurring(self):
        """Find the fsm_recurring generated by the so lines. If no
        fsm_recurring linked, it will be created automatically.
        :return a mapping with the so line id and its linked
        fsm_recurring
        :rtype dict
        """
        # one search for all so lines
        fsm_recurrings = self.env["fsm.recurring"].search(
            [("sale_line_id", "in", self.ids)]
        )
        fsm_recurring_sol_mapping = {
            fsm_recurring.sale_line_id.id: fsm_recurring
            for fsm_recurring in fsm_recurrings
        }
        result = {}
        for so_line in self:
            # If the SO was confirmed, cancelled, set to draft then confirmed,
            # avoid creating a new fsm_recurring.
            fsm_recurring = fsm_recurring_sol_mapping.get(so_line.id)
            # If not found, create one fsm_recurring for the so line
            if not fsm_recurring:
                fsm_recurring = so_line._field_create_fsm_recurring()[so_line.id]
            result[so_line.id] = fsm_recurring
        return result

    def _field_service_generation(self):
        """For service lines, create the field service order. If it already
        exists, it simply links the existing one to the line.
        """
        result = super()._field_service_generation()
        for so_line in self.filtered(
            lambda sol: sol.product_id.field_service_tracking == "recurring"
        ):
            so_line._field_find_fsm_recurring()
        return result
