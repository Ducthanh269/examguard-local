import unittest
from examguard.evaluate import evaluate


class EvaluationTests(unittest.TestCase):
    def labels(self, events):
        return {'complete':True,'subject_id':'p01','session_id':'s01','duration_seconds':3600,'events':events}

    def test_one_prediction_cannot_match_two_truths(self):
        labels=self.labels([{'kind':'phone','start':10,'end':15},{'kind':'phone','start':14,'end':20}])
        result=evaluate([{'kind':'phone','detected_at':14}],labels)
        self.assertEqual(result['true_positive'],1)
        self.assertEqual(result['false_negative'],1)

    def test_duplicate_alert_counts_as_false_positive(self):
        labels=self.labels([{'kind':'phone','start':10,'end':20}])
        result=evaluate([{'kind':'phone','detected_at':12},{'kind':'phone','detected_at':15}],labels)
        self.assertEqual(result['false_positive'],1)
        self.assertEqual(result['precision'],.5)
        self.assertEqual(result['false_alerts_per_monitored_hour'],1)

    def test_no_ground_truth_recall_is_not_invented(self):
        result=evaluate([],self.labels([]))
        self.assertIsNone(result['recall'])
        self.assertIsNone(result['precision'])

    def test_incomplete_labels_rejected(self):
        labels=self.labels([])
        labels['complete']=False
        with self.assertRaises(ValueError):
            evaluate([],labels)

    def test_out_of_bounds_truth_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([],self.labels([{'kind':'phone','start':-2,'end':10}]))

    def test_wrong_kind_cannot_match(self):
        result=evaluate([{'kind':'multiple_faces','detected_at':12}],self.labels([{'kind':'phone','start':10,'end':20}]))
        self.assertEqual(result['true_positive'],0)
        self.assertEqual(result['false_negative'],1)
        self.assertEqual(result['false_positive'],1)
