import tensorflow as tf
import os
import numpy as np
# from prepare_data import load_and_preprocess_image
def load_and_preprocess_image(image_raw, data_augmentation=False):
    # decode
    image_tensor = tf.io.decode_image(contents=image_raw, channels=CHANNELS, dtype=tf.dtypes.float32)
  

    if data_augmentation:
        image = tf.image.random_flip_left_right(image=image_tensor)
        image = tf.image.resize_with_crop_or_pad(image=image,
                                                 target_height=int(IMAGE_HEIGHT * 1.2),
                                                 target_width=int(IMAGE_WIDTH * 1.2))
        image = tf.image.random_crop(value=image, size=[IMAGE_HEIGHT, IMAGE_WIDTH, CHANNELS])
        image = tf.image.random_brightness(image=image, max_delta=0.5)
    else:
        image = tf.image.resize(image_tensor, [IMAGE_HEIGHT, IMAGE_WIDTH])

    return image

# from models import get_model # ???
import cv2
import shutil
import os
import logging
# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set logging level to INFO

# Create file handler and set formatter
file_handler = logging.FileHandler('validation_wrong_class.log')  # Specify the file name
file_handler.setLevel(logging.INFO)  # Set logging level to INFO for the file handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add file handler to logger
logger.addHandler(file_handler)


DEVICE = "gpu"   # cpu or gpu

# some training parameters
EPOCHS = 100
BATCH_SIZE = 8
NUM_CLASSES =  52+2 #52+1
#NUM_CLASSES = 53


#IMAGE_HEIGHT = 224
#IMAGE_WIDTH = 224

# configuration.py
#------InceptionV4 :299x299x3-----------
IMAGE_HEIGHT = 299
IMAGE_WIDTH = 299
CHANNELS = 3


save_model_dir = "saved_model"
save_every_n_epoch = 10
test_image_dir = "2024-12-02"

dataset_dir = "dataset/"
train_dir = dataset_dir + "train"
valid_dir = dataset_dir + "valid"
test_dir = dataset_dir + "test"
train_tfrecord = dataset_dir + "train.tfrecord"
valid_tfrecord = dataset_dir + "valid.tfrecord"
test_tfrecord = dataset_dir + "test.tfrecord"
# VALID_SET_RATIO = 1 - TRAIN_SET_RATIO - TEST_SET_RATIO
TRAIN_SET_RATIO = 0.6
TEST_SET_RATIO = 0.2

def get_class_id(image_root):
    id_cls = {}
    for i, item in enumerate(os.listdir(image_root)):
        if os.path.isdir(os.path.join(image_root, item)):
            id_cls[i] = item
    return id_cls


if __name__ == '__main__':
    # GPU settings
    gpus = tf.config.list_physical_devices('GPU')
    if gpus:
        try:
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            logical_gpus = tf.config.list_logical_devices('GPU')
            print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
        except RuntimeError as e:
            print(e)

  
    #----load pretrain model--------------------------------------
    # model = get_model(idx=14)
    #model.load_weights(filepath=save_model_dir)
    model = tf.saved_model.load(save_model_dir)



#     #------single predict-----------------------------------------

#     #test_image_dir='testone/no/no.jpg'    
#     test_image_dir='testone/a0/_1.png'
    
#     #test_image_dir='testone/a01/a1_1.png'
    
#     #test_image_dir='testone/a04/_1.png'
#     #test_image_dir='testone/a07/_1.png'
#     #test_image_dir='testone/a09/_1.png'


# #    test_image_dir='testone/d/d1.jpg'

# #    test_image_dir='testone/h/h1.jpg'
    
# #    test_image_dir='testone/s/s1.jpg'
    

# #    test_image_dir='testone/err/e13.jpg'
#     file_path=filename='./'+test_image_dir
    
    
#     image_raw = tf.io.read_file(file_path)
#     image_raw_mat = load_and_preprocess_image(image_raw)
    
#     #image_raw=cv2.imread(file_path)
#     #image_raw_mat= cv2.resize(image_raw,(299,299))


#     image_tensor = tf.expand_dims(image_raw_mat, axis=0)
#     pred  = model(image_tensor, training=False)
    
#     confidence= np.array(   tf.math.abs(pred).numpy()  ).max()
#     idx = tf.math.argmax(pred, axis=-1).numpy()[0]

#     #id_cls = get_class_id("./original_dataset")
#     id_cls = get_class_id("./dataset/train")
#     #print(id_cls)
#     for mm in id_cls: print(mm  , id_cls[mm] )

#     print('------single predict-----------------')
#     print( test_image_dir," [The predicted category] of this picture is: {}".format( id_cls[idx])  , ', Confidence=',confidence  ,'predicted classid=',idx )





    # '''
    # from object_detection.core import standard_fields as fields
    # scores=pred
    # detection_fields = fields.DetectionResultFields
    # outputs[detection_fields.detection_scores] = tf.identity(scores, name=detection_fields.detection_scores)
    # '''


    #---------multi-predict---------------------------------------
    import  time
    start_=time.time()


    print('------multi-predict----------------')
    test_image_dir_list=[]
    # test_image_dir=os.path.split( test_image_dir)[0]
    if not test_image_dir:
        test_image_dir = 'original_dataset/' 
    '''
    n_cards=10
    for id_n in range(1,n_cards+1):
        test_image_dir_list.append (test_image_dir.replace('_1','_'+str(id_n) )  )
    '''

    # for a_class_dir in os.listdir(test_image_dir):
    #     a_class_files = os.listdir(os.path.join(test_image_dir, a_class_dir))
    #     # print(a_class_files)
    #     for file_name in a_class_files:
    #         test_image_dir_list.append(   os.path.join(  test_image_dir, a_class_dir, file_name ) )

    # 這邊改為使用該資料夾的所有檔案
    test_image_dir_list = os.listdir(test_image_dir)


    n_cards=test_image_dir_list.__len__()

    # copy wrongly classified images into a folder, for review
    destination_folder = 'wrongly_classified_images'
    os.makedirs(destination_folder, exist_ok=True)
    output_folder = test_image_dir + '_output_predict_imgs'
    os.makedirs(output_folder, exist_ok=True)

    # print(test_image_dir_list)

    for path_m in  test_image_dir_list : 
        # path_m_class = path_m.split('/')[1].split('\\')[0]
        # image_raw = tf.io.read_file(filename='./'+path_m)
        image_raw = tf.io.read_file(filename=test_image_dir+'/'+path_m)
        image_tensor = load_and_preprocess_image(image_raw)

        # 20241205 為了檢驗preprocess有沒有錯誤，寫一個function在local disk寫入preprocess好的tensor轉回image
        def save_image_from_tensor(tensor, output_path):
            # Convert RGB to BGR for OpenCV compatibility
            bgr_image_tensor = tf.reverse(tensor, axis=[-1])  # Swap RGB to BGR
            
            # Convert to NumPy array and scale pixel values to [0, 255]
            image_array = (bgr_image_tensor.numpy() * 255).astype(np.uint8)
            
            # Save the image
            cv2.imwrite(output_path, image_array)
            print(f"Image saved to {output_path}")

        #20241205 save temp image from tensor to see the result of preprocessing
        # save_image_from_tensor(image_tensor, f'processed_image_{path_m}')

        image_tensor = tf.expand_dims(image_tensor, axis=0)

        pred = model(image_tensor, training=False)
       
        confidence= np.array(   tf.math.abs(pred).numpy()  ).max()
        idx = tf.math.argmax(pred, axis=-1).numpy()[0]

        id_cls = get_class_id("./original_dataset_structure_empty")

        # print(id_cls)
        # print( path_m,",predicted category=: {}".format(id_cls[idx])  , ', confidence=', confidence  ,',predicted classidx=',idx )

        # if (path_m_class != id_cls[idx]):
        #     logger.info(f"path_m_class:{str(path_m_class)} , path_m : " + path_m + f",predicted category=: {id_cls[idx]}"  + ', confidence=' + str(confidence) + ',predicted classidx=' + str(idx) )
        #     # Construct the full destination file path
        #     file_name = path_m_class + '_' + os.path.basename(path_m).replace('.png', '.jpg').split('.jpg')[0] + f"_prediction_{id_cls[idx]}" + ".jpg"
        #     destination_file = os.path.join(destination_folder, file_name)
        #     # Copy the file
        #     shutil.copy(path_m, destination_file)

        # 把所有predict結果儲存在destination_folder
        file_name = os.path.basename(path_m).replace('.png', '.jpg').split('.jpg')[0] + f"_pred_{id_cls[idx]}_score_({confidence})" + ".jpg"
        destination_file = os.path.join(output_folder, file_name)
        # print(destination_file)
        # Copy the file
        shutil.copy(test_image_dir+'/'+path_m, destination_file)

    end_=time.time()
    avg_costtime=(end_-start_)/(n_cards+1)
    print('avg_costtime=',avg_costtime)
    