
program hundred;

var
   n,i,s : integer;
   
begin

   readln(n);
   
   s := 0;
   for i:=0 to n do begin
      writeln(i);
      s := s + Sum(i,i);
   end;
end.
   
