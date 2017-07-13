# -*- coding: utf-8 -*-
from __future__ import division
import cv2
import numpy as np
from glob import glob
from scipy import ndimage
from utils.nms import nms
from network.eyenet import EyeNet
from utils.datatools import data_arguement, video_cut_argue

class EyeDetect(object):
    def __init__(self, face_cascade_file, eyes_cascade_file, left_video_dir, right_video_dir, 
                         recover_video_path, image_size=28, image_max_length=320, batch_size=16, num_classes=2, 
                         test_batch=32, lr=0.0001, display_iters=500, test_iters=1000, max_iterations=500):
        # root params
        self.image_max_length = image_max_length
        self.face_cascade_file = face_cascade_file
        self.eyes_cascade_file = eyes_cascade_file
        self.left_video_dir = left_video_dir
        self.right_video_dir = right_video_dir
        self.recover_video_path = recover_video_path
        # train params
        self.image_size = image_size
        self.batch_size = batch_size
        self.num_classes = num_classes
        self.test_batch = test_batch
        self.lr = lr
        self.display_iters = display_iters
        self.test_iters = test_iters
        self.max_iterations = max_iterations
        self.build_model()
    
    def build_model(self):
        self.face_detector = cv2.CascadeClassifier(self.face_cascade_file)   
        self.eyes_detector = cv2.CascadeClassifier(self.eyes_cascade_file)
        self.eyes_selector = EyeNet(image_size=self.image_size,
                                    batch_size=self.batch_size,
                                    num_classes=self.num_classes, 
                                    test_batch=self.test_batch,
                                    lr=self.lr, 
                                    display_iters=self.display_iters, 
                                    test_iters=self.test_iters, 
                                    max_iterations=self.max_iterations)
    
    # image resize
    def resize(self, image):
        width, height = image.shape[1], image.shape[0]
        scale = self.image_max_length / max(width, height)
        image = cv2.resize(image,(int(width*scale),int(height*scale)))
        return image, scale
    
    # train EyeNet
    def train(self, session, data):
        self.eyes_selector.train(session, data)
    
    # function: face detect, eye detect and eye select from a single frame 
    def detect_from_image(self, session, full_image, visualize=False):
        # step1: preprocess, image resize, grayscale, equalizeHist
        image, _ = self.resize(full_image)
        image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image_gray = cv2.equalizeHist(image_gray)
        # face detect
        face_regions = self.face_detector.detectMultiScale(image_gray, 1.05, 4, cv2.cv.CV_HAAR_SCALE_IMAGE, (60,60))
        # eyes detect based on face region
        eyes_regions = []
        for (x, y, w, h) in face_regions:
            face_image = image_gray[y:y+h,x:x+w]
            # resize face, transform to high resolution
            face_image, scale = self.resize(face_image)
            # first eyes detection
            eyes_roi = self.eyes_detector.detectMultiScale(face_image, 1.05, 2, cv2.cv.CV_HAAR_SCALE_IMAGE, (60,60),(120,120))
            # second eyes detection  
            for (ex, ey, ew, eh) in eyes_roi:
                eye = face_image[ey:ey+eh,ex:ex+ew]
                pred = self.eyes_selector.predict(session,eye)
                if pred == 1:
                    eyes_regions.append([x+int(ex/scale),y+int(ey/scale),int(ew/scale),int(eh/scale)]) 
        # apply nms reduce bbox        
        eyes_regions = nms(eyes_regions, thres=0.5)
        # visulize
        if visualize:
            # plot
            for (x, y, w, h) in face_regions:
                cv2.rectangle(image, (x, y), (x+w, y+h), (0, 0, 255), 2)
            for (x, y, w, h) in eyes_regions:
                cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)   
            # 显示标定框
            cv2.imshow("eye detect", image)
            cv2.waitKey(5) 
        # post precess, generate left/right eye boundingbox
        # detect bbox more than 2, return None
        if len(eyes_regions)!=2:
            return None, None
        # convert to (left, right) pair format
        eyes_bndbox = sorted(eyes_regions, key=lambda bbox:bbox[0]+bbox[2]//2)
        eyes_region = [cv2.resize(image_gray[y:y+h,x:x+w],(self.image_size,self.image_size)) for (x,y,w,h) in eyes_bndbox]
        return eyes_bndbox, eyes_region
    
    # function: face detect, eye detect and eye select from a video
    def detect_from_video(self, session, video_path, filters=True):
        # previous left and right eye image, initial to zero
        pre_left = np.zeros((self.image_size,self.image_size),dtype=np.uint8)
        pre_right = np.zeros((self.image_size,self.image_size),dtype=np.uint8)
        # load video file
        video_left_eye_seq, video_right_eye_seq = [], []
        # extract from video
        count, empty = 0, 0
        try:
            cap = cv2.VideoCapture(video_path)
            while(cap.isOpened()):
                ret, frame = cap.read()
                if frame is not None:
                    count += 1
                    frame = ndimage.rotate(frame,270)
                    _,eyes_roi = self.detect_from_image(session, frame, False)
                    if eyes_roi is not None and count > 1:
                        video_left_eye_seq.append((eyes_roi[0]-pre_left)/255.0)
                        video_right_eye_seq.append((eyes_roi[1]-pre_right)/255.0)
                        pre_left = eyes_roi[0].copy()
                        pre_right = eyes_roi[1].copy()
                    else:
                        video_left_eye_seq.append(np.zeros_like(pre_left))
                        video_right_eye_seq.append(np.zeros_like(pre_right))
                        empty += 1
                    #cv2.imwrite('output/{0}_1.jpg'.format(count),pre_left)
                    #cv2.imwrite('output/{0}_2.jpg'.format(count),pre_right)
                if (cv2.waitKey(1) & 0xFF == ord('q')) or frame is None:
                    break
            # When everything done, release the capture
            cap.release()
            cv2.destroyAllWindows()
            loss_frame_rate = empty / count
            #print empty, count
            print '[Step1 Data] Processing video:{0}, #loss:{1}, #total:{2}, loss_rate:{3}'.format(video_path.split('/')[-1], empty, count, loss_frame_rate)
            if loss_frame_rate > 0.5 and filters:
                return None
            else:
                return [video_left_eye_seq, video_right_eye_seq]
        except Exception, e:
            print e
            return None
            
    # function: face detect, eye detect and eye select from video folder
    def detect_from_folder(self, session, video_folder, ext='MP4'):
        video_sets = []
        for path in glob(video_folder+'/*.'+ext):
            seq = self.detect_from_video(session, path)
            if seq is not None:
                video_sets.append(seq)
        return video_sets
    
    # module1 output
    def output_lstm_format(self, session, step_size):
        # generate output
        left_sequence_sets = self.detect_from_folder(session,self.left_video_dir,'MP4')
        right_sequence_sets = self.detect_from_folder(session,self.right_video_dir,'MP4')
        none_sequence = self.detect_from_video(session,self.recover_video_path,filters=False)
        # data arguement
        seq_left_l, seq_left_r = data_arguement(left_sequence_sets, seq_max_length=step_size)
        seq_right_l, seq_right_r = data_arguement(right_sequence_sets, seq_max_length=step_size)
        seq_none_l, seq_none_r = video_cut_argue(none_sequence,cut_length=step_size,cut_stride=5,argue=False)
        # data concate
        data_l = seq_left_l + seq_right_l + seq_none_l
        data_r = seq_left_r + seq_right_r + seq_none_r
        label = [[0,1,0]]*len(seq_left_l)+[[0,0,1]]*len(seq_right_l)+[[1,0,0]]*len(seq_none_l)
        data_l, data_r, label = np.array(data_l), np.array(data_r), np.array(label)
        # data shuffle
        index = np.random.permutation(len(label))
        data_l = data_l[index]
        data_r = data_r[index]
        label = label[index]
        return data_l, data_r, label
        