# -*- coding: utf-8 -*-
import cv2
import numpy as np
import tensorflow as tf
from layers import conv2d, relu, max_pool, fc
from utils.datatools import get_next_batch, data_split

class EyeNet(object):
    def __init__(self,image_size=28,batch_size=16,num_classes=2, test_batch=32, \
                        lr=0.0001, display_iters=500, test_iters=1000, max_iterations=60000):
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
        # input and output
        self.X = tf.placeholder(tf.float32,[None,self.image_size,self.image_size,1])
        self.Y = tf.placeholder(tf.float32,[None,self.num_classes])        
        # output, loss function, optimizer  
        self.output = self.net(self.X)
        self.loss_func = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(self.output,self.Y))
        self.optimizer = tf.train.AdamOptimizer(self.lr).minimize(self.loss_func)
        # val param
        self.correct = tf.reduce_sum(tf.cast(tf.equal(tf.arg_max(self.output,1),tf.arg_max(self.Y,1)),dtype=tf.float32))
        # test param
        self.norm_output = tf.cast(tf.greater_equal(self.output,tf.ones_like(self.output)*0.8), dtype=tf.float32)
        self.result = tf.argmax(self.norm_output,1)
     
    def net(self, X, reuse=None):
        with tf.variable_scope('EyeNet', reuse=reuse):
            conv1 = conv2d(X,output_dims=20,k_h=5,k_w=5,s_h=1,s_w=1,padding='VALID',name='conv1')   
            pool1 = max_pool(conv1,k_h=2,k_w=2,s_h=2,s_w=2,padding='SAME',name='pool1')
            conv2 = conv2d(pool1,output_dims=50,k_h=5,k_w=5,s_h=1,s_w=1,padding='VALID',name='conv2')              
            pool2 = max_pool(conv2,k_h=2,k_w=2,s_h=2,s_w=2,padding='SAME',name='pool2') 
            flatten = tf.reshape(pool2,[-1, pool2.get_shape().as_list()[1]
                                            *pool2.get_shape().as_list()[2]
                                            *pool2.get_shape().as_list()[3]], name='conv_reshape')
            fc1 = fc(flatten, output_dims=500, name='fc1')
            relu1 = relu(fc1, name='relu1')
            out = fc(relu1, output_dims=2, name='output')
            return out
    
    def train(self, session, data):
        # prepare data
        self.data = data_split(X=data[0],Y=data[1],train_rate=0.8)
        print '[Step1 Data] Train samples:{0}, valid samples:{1}'.format(len(self.data[0]), len(self.data[3]))
        # train step by step
        for iters in range(self.max_iterations):
            batch_x, batch_y = get_next_batch(self.data[0], self.data[1], iters, self.batch_size)
            loss, _ = session.run([self.loss_func, self.optimizer],feed_dict={self.X:batch_x, self.Y:batch_y})
            if iters % self.display_iters == 0:
                print '[Step1 Train] EyeNet Iters:{0}, loss:{1}'.format(iters,loss)
            if iters % self.test_iters == 0:
                self.val_internal(session)
    
    def val_internal(self, session):
        max_batches = len(self.data[2]) // self.test_batch
        rights = 0.0
        for iters in range(max_batches):
            batch_x, batch_y = get_next_batch(self.data[2], self.data[3], iters, self.test_batch)
            sums = session.run(self.correct,feed_dict={self.X:batch_x,self.Y:batch_y})
            rights += sums
        print '[Step1 Valid] EyeNet val accuracy:{0}'.format(rights/len(self.data[2]))   
    
    def predict(self, session, image):
        # image resize
        image = cv2.resize(image,(self.image_size,self.image_size))
        image = np.reshape(image,[1,self.image_size,self.image_size,1])
        pred = session.run(self.result, feed_dict={self.X:image})
        return pred[0]