# Extra tests for the measurement paper (script 14, 2026-11-07)

## 1. National year effects (JT02 main, annual change in same-county share, points)

 year  n_states  median_change  mean_change  n_negative  sign_test_p  year_effect_nofe  se_nofe
 2005        49        -0.3331      -0.3588          42       0.0000           -0.3588   0.0619
 2006        49        -0.2243      -0.1782          36       0.0007           -0.1782   0.1094
 2007        49        -2.6132      -2.4157          49       0.0000           -2.4157   0.1499
 2008        49        -0.5406      -0.5300          45       0.0000           -0.5300   0.0654
 2009        49        -1.6876      -1.7014          49       0.0000           -1.7014   0.1020
 2010        49        -0.3238      -0.3251          38       0.0001           -0.3251   0.0579
 2011        50        -0.6130      -0.9547          42       0.0000           -0.9547   0.1688

The 2007 year effect is -6.5 SD of the other non-step years' effects below their mean. Share of placebo state-years (2005, 2006, 2008, 2010, 2011) with a drop at least as large as the median 2007 state: 0.020. KS test 2007 vs placebo D = 0.77, p = 4.6e-25; Mann-Whitney p = 7.2e-21.


## 2. Same-county share by age band (JT00 main), 2004-2010

      same_cty_age1             same_cty_age2             same_cty_age3            
state            il    ks    mo            il    ks    mo            il    ks    mo
yr                                                                                 
2004           63.7  67.6  58.6          64.9  71.8  59.0          69.0  73.8  63.1
2005           62.8  67.2  58.2          64.1  71.3  58.8          68.2  73.3  62.9
2006           62.5  67.7  58.0          63.4  71.8  58.5          67.8  73.7  62.4
2007           59.6  64.7  54.9          60.7  69.1  55.7          65.1  71.0  59.1
2008           60.9  64.1  54.5          61.7  68.6  55.5          65.5  70.3  59.3
2009           60.7  63.3  53.2          61.1  67.0  53.8          64.7  69.1  57.6
2010           60.7  62.7  52.7          61.1  66.7  53.3          64.5  68.8  57.0

Year-on-year change in 2007 by age band (points):

state  same_cty_age1_d  same_cty_age2_d  same_cty_age3_d
   mo            -3.11            -2.76            -3.33
   ks            -3.10            -2.70            -2.72
   il            -2.92            -2.69            -2.76

Year-on-year change in 2009 by age band (points):

state  same_cty_age1_d  same_cty_age2_d  same_cty_age3_d
   mo            -1.29            -1.69            -1.67
   ks            -0.84            -1.56            -1.21
   il            -0.21            -0.52            -0.74

## 3. Share of metro jobs held by residents > 100 miles away (JT00), 2006-2008

year           2006  2007  2008  d_2007
metro                                  
capegirardeau   7.0   9.5   9.3     2.5
columbia       11.7  14.6  13.8     2.9
jeffcity        9.5  10.2  10.8     0.7
joplin          5.9   7.7   8.9     1.8
kansascity      4.1   4.8   5.5     0.7
springfield     7.0   8.3   9.0     1.3
stjoseph        4.9   5.8   6.7     0.9
stlouis         3.1   3.9   4.3     0.8
