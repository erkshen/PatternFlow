
import tensorflow as tf

class GaussInteger():
    def __init__(self, real, imag):
        """
        Initialises the class. real is the real part and imag is the
        imaginary part.
        """
        # Check input type.
        if (type(real) is not int or type(imag) is not int):
            raise TypeError("Inputs a and b of GaussInteger(a, b) must be"
                            + " ints.")

        # Cast variables to create complex number.
        self.real = tf.dtypes.cast(tf.constant([real]), tf.float32)
        self.imag = tf.dtypes.cast(tf.constant([imag]), tf.float32)
        self.num = tf.complex(self.real, self.imag)

    def getNum(self):
        """
        Returns the complex number as a python complex type.
        """
        with tf.Session() as sess:
            return complex(self.num.eval()[0])
