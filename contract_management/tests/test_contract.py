"""
Contract Management Module — Full Test Suite
=============================================
Covers:
  - Auto-numbering on create
  - Full workflow for each contract type (Frame MSA, Lump Sum, Unit Rate CTR, Daywork T&M)
  - All ValidationError guards
  - Contract line computations (subtotal, lines_total)
  - onchange: parent_frame_id populates lines, contractor_id clears frame
  - Evaluation: total_amount, avg_profitability, is_lowest, evaluated_partner_ids
  - eval_comparison_html HTML generation
  - Justification wizard (cancel, resubmit_requestor, resubmit_contracting)
  - Approver activity notification
  - responsible_id follower subscription via write()

Run with:
  odoo-bin -d <db> --test-enable -i contract_management --stop-after-init
  # or
  odoo-bin -d <db> --test-tags contract_management
"""
import base64
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tests import tagged


# ---------------------------------------------------------------------------
# Base class — shared helpers and setup
# ---------------------------------------------------------------------------

@tagged('post_install', '-at_install', 'contract_management')
class TestContractBase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_a = cls.env['res.partner'].create({'name': 'Contractor Alpha'})
        cls.partner_b = cls.env['res.partner'].create({'name': 'Contractor Beta'})
        cls.partner_c = cls.env['res.partner'].create({'name': 'Contractor Gamma'})

        cls.user_requester = cls.env['res.users'].create({
            'name': 'Test Requester',
            'login': 'test_requester_cm',
            'email': 'requester@test.com',
            'groups_id': [(4, cls.env.ref('contract_management.group_requester').id)],
        })
        cls.user_team = cls.env['res.users'].create({
            'name': 'Test Team',
            'login': 'test_team_cm',
            'email': 'team@test.com',
            'groups_id': [(4, cls.env.ref('contract_management.group_subcontractor_team').id)],
        })
        cls.user_mgmt = cls.env['res.users'].create({
            'name': 'Test Manager',
            'login': 'test_mgmt_cm',
            'email': 'manager@test.com',
            'groups_id': [(4, cls.env.ref('contract_management.group_management').id)],
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _attachment(self, contract, name='boq.pdf'):
        """Return an ir.attachment linked to the contract."""
        return self.env['ir.attachment'].create({
            'name': name,
            'datas': base64.b64encode(b'dummy'),
            'res_model': 'contract.contract',
            'res_id': contract.id,
        })

    def _signed_attachment(self, contract):
        return self._attachment(contract, name='signed_contract.pdf')

    def _new_contract(self, contract_type, **kwargs):
        vals = {
            'title': f'Test {contract_type}',
            'contract_type': contract_type,
            'responsible_id': self.user_requester.id,
        }
        vals.update(kwargs)
        return self.env['contract.contract'].create(vals)

    def _add_boq(self, contract):
        att = self._attachment(contract)
        contract.attachment_ids = [(4, att.id)]
        return att

    def _add_approver(self, contract):
        return self.env['contract.approver'].create({
            'contract_id': contract.id,
            'user_id': self.user_mgmt.id,
        })

    def _add_evaluation(self, contract, partner, unit_rate=200.0, qty=5.0, awarded_rate=None):
        if awarded_rate is None:
            awarded_rate = unit_rate * 1.1
        return self.env['contract.evaluation'].create({
            'contract_id': contract.id,
            'partner_id': partner.id,
            'is_recommended': False,
            'line_ids': [(0, 0, {
                'description': 'Work Item',
                'qty': qty,
                'uom': 'm2',
                'unit_rate': unit_rate,
                'awarded_rate': awarded_rate,
            })],
        })

    def _active_frame(self, partner=None):
        """Create a Frame Agreement forced into 'active' state."""
        partner = partner or self.partner_a
        frame = self._new_contract('frame_msa', partner_id=partner.id)
        frame.write({'state': 'active'})
        self.env['contract.line'].create({
            'contract_id': frame.id,
            'description': 'Excavation',
            'qty': 100.0,
            'uom': 'm3',
            'unit_price': 50.0,
        })
        return frame


# ---------------------------------------------------------------------------
# 1. Creation & Sequencing
# ---------------------------------------------------------------------------

class TestContractCreation(TestContractBase):

    def test_auto_sequence(self):
        """Each new contract gets a unique auto-generated number."""
        c1 = self._new_contract('lump_sum_ctr')
        c2 = self._new_contract('lump_sum_ctr')
        self.assertNotEqual(c1.name, 'New', "Contract should have a sequence number")
        self.assertNotEqual(c1.name, c2.name, "Each contract should have a unique number")

    def test_default_state_is_draft(self):
        c = self._new_contract('frame_msa')
        self.assertEqual(c.state, 'draft')

    def test_default_responsible_is_current_user(self):
        c = self.env['contract.contract'].create({
            'title': 'Default Responsible Test',
            'contract_type': 'lump_sum_ctr',
        })
        self.assertEqual(c.responsible_id, self.env.user)


# ---------------------------------------------------------------------------
# 2. Frame Agreement / MSA — full workflow
# ---------------------------------------------------------------------------

class TestFrameMSAWorkflow(TestContractBase):

    def setUp(self):
        super().setUp()
        self.contract = self._new_contract('frame_msa')

    def test_submit_review(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.assertEqual(self.contract.state, 'review')

    def test_submit_without_attachment_raises(self):
        with self.assertRaises(ValidationError):
            self.contract.action_submit_review()

    def test_reviewed_goes_to_rfq_processing(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.assertEqual(self.contract.state, 'rfq_processing')

    def test_rfq_proceed_goes_to_evaluation(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self.assertEqual(self.contract.state, 'evaluation')

    def test_rfq_cancel_opens_wizard(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        result = self.contract.action_rfq_cancel()
        self.assertEqual(result['res_model'], 'contract.justification.wizard')

    def test_proceed_approval_without_evaluations_raises(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_approver(self.contract)
        with self.assertRaises(ValidationError):
            self.contract.action_proceed_approval()

    def test_proceed_approval_without_approvers_raises(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        with self.assertRaises(ValidationError):
            self.contract.action_proceed_approval()

    def test_proceed_approval_goes_to_pending(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_proceed_approval()
        self.assertEqual(self.contract.state, 'pending_approval')

    def test_approve_goes_to_finalization(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_proceed_approval()
        self.contract.action_approve()
        self.assertEqual(self.contract.state, 'finalization')

    def test_finalization_without_signed_copy_raises(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_proceed_approval()
        self.contract.action_approve()
        self.contract.partner_id = self.partner_a
        with self.assertRaises(ValidationError):
            self.contract.action_finalization_proceed()

    def test_finalization_without_counterparty_raises(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_proceed_approval()
        self.contract.action_approve()
        signed = self._signed_attachment(self.contract)
        self.contract.signed_copy_ids = [(4, signed.id)]
        with self.assertRaises(ValidationError):
            self.contract.action_finalization_proceed()

    def test_full_workflow_to_completed(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_proceed_approval()
        self.contract.action_approve()
        signed = self._signed_attachment(self.contract)
        self.contract.signed_copy_ids = [(4, signed.id)]
        self.contract.partner_id = self.partner_a
        self.contract.action_finalization_proceed()
        self.assertEqual(self.contract.state, 'active')
        self.contract.action_active_proceed()
        self.assertEqual(self.contract.state, 'completed')


# ---------------------------------------------------------------------------
# 3. Unit Rate CTR — different path (no RFQ/Evaluation)
# ---------------------------------------------------------------------------

class TestUnitRateCTRWorkflow(TestContractBase):

    def setUp(self):
        super().setUp()
        self.frame = self._active_frame(partner=self.partner_a)
        self.contract = self._new_contract(
            'unit_rate_ctr',
            contractor_id=self.partner_a.id,
            parent_frame_id=self.frame.id,
        )

    def test_reviewed_unit_rate_requires_approvers(self):
        self._add_boq(self.contract)
        self.contract.action_submit_review()
        with self.assertRaises(ValidationError):
            self.contract.action_reviewed()

    def test_reviewed_unit_rate_goes_to_pending_approval(self):
        """Unit Rate CTR skips RFQ and Evaluation — goes straight to pending_approval."""
        self._add_boq(self.contract)
        self._add_approver(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.assertEqual(self.contract.state, 'pending_approval')

    def test_full_unit_rate_workflow(self):
        self._add_boq(self.contract)
        self._add_approver(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        self.assertEqual(self.contract.state, 'pending_approval')
        self.contract.action_approve()
        self.assertEqual(self.contract.state, 'finalization')
        signed = self._signed_attachment(self.contract)
        self.contract.signed_copy_ids = [(4, signed.id)]
        self.contract.partner_id = self.partner_a
        self.contract.action_finalization_proceed()
        self.assertEqual(self.contract.state, 'active')
        self.contract.action_active_proceed()
        self.assertEqual(self.contract.state, 'completed')

    def test_reject_opens_wizard(self):
        self._add_boq(self.contract)
        self._add_approver(self.contract)
        self.contract.action_submit_review()
        self.contract.action_reviewed()
        result = self.contract.action_reject()
        self.assertEqual(result['res_model'], 'contract.justification.wizard')


# ---------------------------------------------------------------------------
# 4. Lump Sum CTR — same RFQ path as Frame MSA
# ---------------------------------------------------------------------------

class TestLumpSumWorkflow(TestContractBase):

    def test_full_lump_sum_workflow(self):
        c = self._new_contract('lump_sum_ctr')
        self._add_boq(c)
        c.action_submit_review()
        self.assertEqual(c.state, 'review')
        c.action_reviewed()
        self.assertEqual(c.state, 'rfq_processing')
        c.action_rfq_proceed()
        self.assertEqual(c.state, 'evaluation')
        self._add_evaluation(c, self.partner_a)
        self._add_approver(c)
        c.action_proceed_approval()
        self.assertEqual(c.state, 'pending_approval')
        c.action_approve()
        self.assertEqual(c.state, 'finalization')
        signed = self._signed_attachment(c)
        c.signed_copy_ids = [(4, signed.id)]
        c.partner_id = self.partner_a
        c.action_finalization_proceed()
        self.assertEqual(c.state, 'active')


# ---------------------------------------------------------------------------
# 5. Daywork / T&M — same RFQ path
# ---------------------------------------------------------------------------

class TestDayworkWorkflow(TestContractBase):

    def test_daywork_goes_to_rfq_after_review(self):
        c = self._new_contract('daywork_tm')
        self._add_boq(c)
        c.action_submit_review()
        c.action_reviewed()
        self.assertEqual(c.state, 'rfq_processing')


# ---------------------------------------------------------------------------
# 6. Resubmit / Cancel wizard actions
# ---------------------------------------------------------------------------

class TestWizardActions(TestContractBase):

    def setUp(self):
        super().setUp()
        self.contract = self._new_contract('lump_sum_ctr')
        self._add_boq(self.contract)
        self.contract.action_submit_review()

    def test_resubmit_requestor_from_review(self):
        result = self.contract.action_resubmit_requestor()
        self.assertEqual(result['res_model'], 'contract.justification.wizard')

    def _run_wizard(self, action_code, label, contract=None):
        contract = contract or self.contract
        wizard = self.env['contract.justification.wizard'].create({
            'contract_id': contract.id,
            'action_code': action_code,
            'action_label': label,
            'justification': 'Test justification reason',
        })
        wizard.action_confirm()
        return contract

    def test_wizard_cancel_sets_cancelled(self):
        contract = self._run_wizard('cancel', 'Cancel Contract')
        self.assertEqual(contract.state, 'cancelled')

    def test_wizard_resubmit_requestor_sets_draft(self):
        contract = self._run_wizard('resubmit_requestor', 'Resubmit to Requestor')
        self.assertEqual(contract.state, 'draft')

    def test_wizard_resubmit_contracting_sets_evaluation(self):
        # Force to pending_approval first
        self._add_evaluation(self.contract, self.partner_a)
        self._add_approver(self.contract)
        self.contract.action_reviewed()
        self.contract.action_rfq_proceed()
        self.contract.action_proceed_approval()
        contract = self._run_wizard('resubmit_contracting', 'Resubmit to Contracting')
        self.assertEqual(contract.state, 'evaluation')

    def test_wizard_posts_chatter_message(self):
        before = len(self.contract.message_ids)
        self._run_wizard('cancel', 'Cancel Contract')
        after = len(self.contract.message_ids)
        self.assertGreater(after, before, "Wizard should post a message to the chatter")

    def test_wizard_requires_justification(self):
        """Justification field is required=True — creating without it should fail."""
        with self.assertRaises(Exception):
            self.env['contract.justification.wizard'].create({
                'contract_id': self.contract.id,
                'action_code': 'cancel',
                'action_label': 'Cancel',
                # no justification
            })


# ---------------------------------------------------------------------------
# 7. Contract Lines
# ---------------------------------------------------------------------------

class TestContractLines(TestContractBase):

    def test_subtotal_computed(self):
        line = self.env['contract.line'].create({
            'contract_id': self._new_contract('frame_msa').id,
            'description': 'Paint',
            'qty': 10.0,
            'uom': 'm2',
            'unit_price': 25.0,
        })
        self.assertAlmostEqual(line.subtotal, 250.0)

    def test_subtotal_zero_qty(self):
        c = self._new_contract('unit_rate_ctr')
        line = self.env['contract.line'].create({
            'contract_id': c.id,
            'description': 'Excavation',
            'qty': 0.0,
            'uom': 'm3',
            'unit_price': 50.0,
        })
        self.assertAlmostEqual(line.subtotal, 0.0)

    def test_lines_total_sums_all_lines(self):
        c = self._new_contract('lump_sum_ctr')
        self.env['contract.line'].create([
            {'contract_id': c.id, 'description': 'A', 'qty': 2.0, 'unit_price': 100.0},
            {'contract_id': c.id, 'description': 'B', 'qty': 3.0, 'unit_price': 200.0},
        ])
        self.assertAlmostEqual(c.lines_total, 800.0)  # 2×100 + 3×200

    def test_lines_total_updates_on_qty_change(self):
        c = self._new_contract('lump_sum_ctr')
        line = self.env['contract.line'].create({
            'contract_id': c.id, 'description': 'A', 'qty': 1.0, 'unit_price': 100.0,
        })
        self.assertAlmostEqual(c.lines_total, 100.0)
        line.qty = 5.0
        self.assertAlmostEqual(c.lines_total, 500.0)


# ---------------------------------------------------------------------------
# 8. Parent Frame onchange — line population
# ---------------------------------------------------------------------------

class TestFrameOnchange(TestContractBase):

    def test_parent_frame_onchange_populates_lines(self):
        frame = self._active_frame(partner=self.partner_a)
        # frame has 1 line: Excavation, qty=100, unit_price=50
        ctr = self._new_contract(
            'unit_rate_ctr',
            contractor_id=self.partner_a.id,
        )
        # Simulate onchange
        ctr._origin = ctr  # needed for onchange context
        ctr.parent_frame_id = frame
        ctr._onchange_parent_frame_id()
        self.assertEqual(len(ctr.line_ids), 1)
        self.assertEqual(ctr.line_ids[0].description, 'Excavation')
        self.assertAlmostEqual(ctr.line_ids[0].unit_price, 50.0)

    def test_contractor_onchange_clears_frame(self):
        frame = self._active_frame(partner=self.partner_a)
        ctr = self._new_contract(
            'unit_rate_ctr',
            contractor_id=self.partner_a.id,
            parent_frame_id=frame.id,
        )
        ctr.contractor_id = self.partner_b
        ctr._onchange_contractor_id()
        self.assertFalse(ctr.parent_frame_id)


# ---------------------------------------------------------------------------
# 9. Commercial Evaluation
# ---------------------------------------------------------------------------

class TestEvaluation(TestContractBase):

    def setUp(self):
        super().setUp()
        self.contract = self._new_contract('lump_sum_ctr')

    def test_evaluation_total_amount(self):
        ev = self._add_evaluation(self.contract, self.partner_a, unit_rate=200.0, qty=5.0)
        # total = 5 * 200 = 1000
        self.assertAlmostEqual(ev.total_amount, 1000.0)

    def test_evaluation_avg_profitability(self):
        ev = self.env['contract.evaluation'].create({
            'contract_id': self.contract.id,
            'partner_id': self.partner_a.id,
            'line_ids': [(0, 0, {
                'description': 'Item',
                'qty': 10.0,
                'uom': 'unit',
                'unit_rate': 100.0,
                'awarded_rate': 110.0,   # 10% profit
            })],
        })
        self.assertAlmostEqual(ev.avg_profitability, 10.0, places=1)

    def test_evaluation_avg_profitability_negative(self):
        ev = self.env['contract.evaluation'].create({
            'contract_id': self.contract.id,
            'partner_id': self.partner_a.id,
            'line_ids': [(0, 0, {
                'description': 'Item',
                'qty': 10.0,
                'uom': 'unit',
                'unit_rate': 100.0,
                'awarded_rate': 90.0,   # -10% (loss)
            })],
        })
        self.assertAlmostEqual(ev.avg_profitability, -10.0, places=1)

    def test_is_lowest_single_evaluation(self):
        ev = self._add_evaluation(self.contract, self.partner_a, unit_rate=100.0, qty=5.0)
        # Only one evaluation — it IS the lowest
        ev.invalidate_recordset()
        self.assertTrue(ev.is_lowest)

    def test_is_lowest_two_evaluations(self):
        ev_low = self._add_evaluation(self.contract, self.partner_a, unit_rate=80.0, qty=5.0)
        ev_high = self._add_evaluation(self.contract, self.partner_b, unit_rate=120.0, qty=5.0)
        ev_low.invalidate_recordset()
        ev_high.invalidate_recordset()
        self.assertTrue(ev_low.is_lowest)
        self.assertFalse(ev_high.is_lowest)

    def test_evaluated_partner_ids(self):
        self._add_evaluation(self.contract, self.partner_a)
        self._add_evaluation(self.contract, self.partner_b)
        self.assertIn(self.partner_a, self.contract.evaluated_partner_ids)
        self.assertIn(self.partner_b, self.contract.evaluated_partner_ids)

    def test_eval_comparison_html_no_evals(self):
        html = self.contract.eval_comparison_html
        self.assertIn('No evaluations', html)

    def test_eval_comparison_html_with_evals(self):
        self._add_evaluation(self.contract, self.partner_a, unit_rate=100.0, qty=5.0)
        self._add_evaluation(self.contract, self.partner_b, unit_rate=90.0, qty=5.0)
        html = self.contract.eval_comparison_html
        self.assertIn('Contractor Alpha', html)
        self.assertIn('Contractor Beta', html)
        self.assertIn('TOTAL', html)
        self.assertIn('<table', html)

    def test_eval_line_onchange_copies_from_contract_line(self):
        c = self._new_contract('lump_sum_ctr')
        cl = self.env['contract.line'].create({
            'contract_id': c.id,
            'description': 'Painting',
            'qty': 20.0,
            'uom': 'm2',
            'unit_price': 30.0,
        })
        ev = self.env['contract.evaluation'].create({
            'contract_id': c.id,
            'partner_id': self.partner_a.id,
        })
        eval_line = self.env['contract.evaluation.line'].new({
            'evaluation_id': ev.id,
            'contract_line_id': cl.id,
        })
        eval_line._onchange_contract_line_id()
        self.assertEqual(eval_line.description, 'Painting')
        self.assertAlmostEqual(eval_line.qty, 20.0)
        self.assertEqual(eval_line.uom, 'm2')


# ---------------------------------------------------------------------------
# 10. Approver notifications
# ---------------------------------------------------------------------------

class TestApproverNotification(TestContractBase):

    def test_notify_approvers_schedules_activity(self):
        c = self._new_contract('lump_sum_ctr')
        self._add_boq(c)
        self._add_approver(c)
        c.action_submit_review()
        c.action_reviewed()
        c.action_rfq_proceed()
        self._add_evaluation(c, self.partner_a)
        # Before action_proceed_approval
        activities_before = self.env['mail.activity'].search([
            ('res_model', '=', 'contract.contract'),
            ('res_id', '=', c.id),
        ])
        c.action_proceed_approval()
        activities_after = self.env['mail.activity'].search([
            ('res_model', '=', 'contract.contract'),
            ('res_id', '=', c.id),
        ])
        self.assertGreater(len(activities_after), len(activities_before),
                           "An activity should be created for the approver")

    def test_notify_approvers_unit_rate(self):
        """Unit Rate CTR notifies approvers when moving to pending_approval via action_reviewed."""
        frame = self._active_frame(partner=self.partner_a)
        c = self._new_contract('unit_rate_ctr', contractor_id=self.partner_a.id,
                               parent_frame_id=frame.id)
        self._add_boq(c)
        self._add_approver(c)
        c.action_submit_review()
        c.action_reviewed()
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'contract.contract'),
            ('res_id', '=', c.id),
            ('user_id', '=', self.user_mgmt.id),
        ])
        self.assertTrue(activities, "Approver should have a pending activity")


# ---------------------------------------------------------------------------
# 11. Responsible follower subscription (write method)
# ---------------------------------------------------------------------------

class TestFollowerSubscription(TestContractBase):

    def test_write_responsible_adds_follower(self):
        c = self._new_contract('lump_sum_ctr')
        new_user = self.env['res.users'].create({
            'name': 'New Responsible',
            'login': 'new_resp_cm',
            'email': 'newresp@test.com',
            'groups_id': [(4, self.env.ref('contract_management.group_requester').id)],
        })
        c.write({'responsible_id': new_user.id})
        follower_partners = c.message_follower_ids.mapped('partner_id')
        self.assertIn(new_user.partner_id, follower_partners,
                      "New responsible should be added as a follower")

    def test_write_same_responsible_no_duplicate_error(self):
        """Updating responsible_id to the same person should not raise an error."""
        c = self._new_contract('lump_sum_ctr')
        try:
            c.write({'responsible_id': self.user_requester.id})
        except Exception as e:
            self.fail(f"Writing same responsible raised an exception: {e}")


# ---------------------------------------------------------------------------
# 12. Security / Access Rights (basic smoke tests)
# ---------------------------------------------------------------------------

class TestAccessRights(TestContractBase):

    def test_viewer_can_read(self):
        user_viewer = self.env['res.users'].create({
            'name': 'Viewer',
            'login': 'viewer_cm',
            'email': 'viewer@test.com',
            'groups_id': [(4, self.env.ref('contract_management.group_viewer').id)],
        })
        c = self._new_contract('lump_sum_ctr')
        contracts = self.env['contract.contract'].with_user(user_viewer).search([('id', '=', c.id)])
        self.assertEqual(len(contracts), 1)

    def test_requester_can_create(self):
        Contract = self.env['contract.contract'].with_user(self.user_requester)
        c = Contract.create({'title': 'Req Contract', 'contract_type': 'lump_sum_ctr'})
        self.assertTrue(c.id)

    def test_requester_cannot_delete(self):
        c = self._new_contract('lump_sum_ctr')
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            c.with_user(self.user_requester).unlink()

    def test_team_can_delete(self):
        c = self._new_contract('lump_sum_ctr')
        # Should not raise
        c.with_user(self.user_team).unlink()