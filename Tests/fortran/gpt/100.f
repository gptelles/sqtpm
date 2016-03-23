      program main
      integer i, n
 
      read(*,*) n
      do 10 i = 0, n
         write(*,1000) i
 10   continue
 1000 format (I0,I0)
      end


