from pathlib import Path
import tempfile
import unittest
import numpy as np
import cv2

from examguard.vision import kabsch_residual, iou, FaceAnalyzer, PhoneDetector
from examguard.config import Config
from examguard.evidence import EvidenceRecorder
from examguard.engine import Event

ROOT=Path(__file__).resolve().parents[1]


class GeometryTests(unittest.TestCase):
    def test_kabsch_preserves_shape_across_translation_and_rotation(self):
        points=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],dtype=float)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]],dtype=float)
        transformed=points@rotation*2+np.array([7,8,9])
        self.assertLess(kabsch_residual(points,transformed),1e-10)

    def test_iou_disjoint(self):
        self.assertEqual(iou([0,0,1,1],[2,2,3,3]),0)

    def test_evidence_clip_can_be_read(self):
        with tempfile.TemporaryDirectory() as folder:
            callbacks=[]
            recorder=EvidenceRecorder(folder,Config(pre_roll_seconds=1,post_roll_seconds=1),lambda *x:callbacks.append(x))
            frame=np.full((360,640,3),120,dtype=np.uint8)
            for i in range(11): recorder.push(frame,i*.1)
            event=Event('phone',0,1,'test')
            recorder.start(event)
            for i in range(11,24): recorder.push(frame,i*.1)
            recorder.close()
            path=Path(callbacks[-1][1])
            self.assertEqual(callbacks[-1][2],'ready')
            cap=cv2.VideoCapture(str(path))
            ok,image=cap.read()
            cap.release()
            self.assertTrue(ok)
            self.assertEqual(image.shape[:2],(360,640))


@unittest.skipUnless((ROOT/'models'/'face_landmarker.task').exists() and (ROOT/'models'/'yolox.onnx').exists(),'Models not installed')
class ModelSmokeTests(unittest.TestCase):
    def test_real_models_execute_on_blank_frame(self):
        cv2.setNumThreads(2)
        frame=np.full((480,640,3),120,dtype=np.uint8)
        face=FaceAnalyzer(ROOT/'models'/'face_landmarker.task')
        try:
            obs,boxes=face.analyze(frame,0)
            self.assertEqual(obs.face_count,0)
            self.assertEqual(boxes,[])
        finally:
            face.close()
        detector=PhoneDetector(ROOT/'models'/'yolox.onnx')
        boxes,score,track=detector.detect(frame)
        self.assertFalse(boxes)
        self.assertEqual(score,0)
